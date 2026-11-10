"""Streamlit + Plotly port of hearthstone.html.

A heatmap of how many collectible minions share each pair of stat values, with
filters on tribe / class / set / mechanic / stat total. Click a cell to list the
minions in it, with links to their wiki pages.

    pip install -r requirements.txt
    streamlit run hearthstone_app.py
"""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.colors as pc
import plotly.graph_objects as go
import streamlit as st

CARDS_URL = "https://api.hearthstonejson.com/v1/latest/enUS/cards.collectible.json"
# Offline fallback: byte-for-byte copies of the API response, with the fetch time in the file name
# (cards.collectible_YYYYMMDDTHHMMSSZ.json). The newest one is used. Refresh with `python update_cache.py`.
CACHE_DIR = Path(__file__).parent / "data"
CACHE_PREFIX = "cards.collectible_"
CACHE_TIME_FORMAT = "%Y%m%dT%H%M%SZ"

# Player-facing keywords; any other mechanic tag is treated as an internal tag.
# Source of truth: https://hearthstone.wiki.gg/wiki/Category:Keywords
# Keep in sync with PUBLIC_MECHANICS in hearthstone.html.
PUBLIC_MECHANICS = {
    "CHARGE", "COLOSSAL", "CORRUPT", "DREDGE", "ECHO", "EXCAVATE", "FORGE", "FRENZY", "GIGANTIFY",
    "HONORABLE_KILL", "INFUSE", "INSPIRE", "JADE_GOLEM", "MAGNETIC", "MANATHIRST", "MINIATURIZE",
    "OVERKILL", "QUICKDRAW", "SPELLBURST", "STARSHIP_PIECE", "TITAN", "TWINSPELL",
    "BATTLECRY", "CHOOSE_ONE", "COMBO", "DEATHRATTLE", "DISCOVER", "DIVINE_SHIELD", "ELUSIVE", "FREEZE",
    "LIFESTEAL", "OUTCAST", "OVERHEAL", "OVERLOAD", "POISONOUS", "REBORN", "RUSH", "SPELLPOWER",
    "STEALTH", "TAUNT", "TRADEABLE", "WINDFURY",
}

# Perceptually uniform and readable with common color vision deficiencies, because the cell value
# is carried by lightness as well as hue.
COLORSCALE = "Viridis"

AXES = {"attack": "Attack", "health": "Health", "cost": "Mana cost", "total": "Stat total"}
SEPARATOR = "────────"
MAX_HOVER_NAMES = 12


def fetch_live_bytes() -> bytes:
    """The API response body, untouched (raises on network/HTTP errors)."""
    # Send our own User-Agent in case the API's CDN rejects urllib's default one.
    req = urllib.request.Request(CARDS_URL, headers={"User-Agent": "hearthstone-card-stat-correlations"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def write_cache(raw: bytes, fetched_at: datetime, cache_dir: Path = CACHE_DIR) -> Path:
    """Save the API response exactly as received; the fetch time goes in the file name."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{CACHE_PREFIX}{fetched_at.strftime(CACHE_TIME_FORMAT)}.json"
    path.write_bytes(raw)
    return path


def read_latest_cache(cache_dir: Path = CACHE_DIR) -> tuple[list[dict], datetime]:
    """The newest cached response and the time it was fetched (parsed from its file name)."""
    # The timestamp format sorts chronologically as plain text.
    newest = max(cache_dir.glob(f"{CACHE_PREFIX}*.json"), default=None)
    if newest is None:
        raise FileNotFoundError(f"no {CACHE_PREFIX}*.json files in {cache_dir}")
    stamp = newest.stem[len(CACHE_PREFIX):]
    fetched_at = datetime.strptime(stamp, CACHE_TIME_FORMAT).replace(tzinfo=timezone.utc)
    return json.loads(newest.read_bytes()), fetched_at


def normalize(cards: list[dict]) -> pd.DataFrame:
    """Raw API cards to one row per minion (list-valued tag columns)."""
    cards = pd.DataFrame(cards)
    minions = cards[cards["type"] == "MINION"].dropna(subset=["cost", "attack", "health"]).copy()
    minions[["cost", "attack", "health"]] = minions[["cost", "attack", "health"]].astype(int)
    minions["total"] = minions["attack"] + minions["health"]

    # Cards can have several tribes (`races`) and several classes (`classes`, for multi-class
    # cards, which then have no `cardClass`). Keep these as list columns and filter by membership
    # so each card still counts exactly once in the unfiltered grid.
    for col in ("races", "classes", "mechanics", "race", "cardClass"):
        if col not in minions:
            minions[col] = None

    def as_list(multi, single):
        if isinstance(multi, list) and multi:
            return multi
        return [single] if isinstance(single, str) and single else []

    minions["races"] = [as_list(a, b) for a, b in zip(minions["races"], minions["race"])]
    minions["classes"] = [as_list(a, b) for a, b in zip(minions["classes"], minions["cardClass"])]
    minions["mechanics"] = [m if isinstance(m, list) else [] for m in minions["mechanics"]]
    minions["sets"] = [[s] if isinstance(s, str) else [] for s in minions["set"]]
    return minions[["name", "dbfId", "cost", "attack", "health", "total", "races", "classes", "sets", "mechanics"]]


def fmt_utc(when: datetime) -> str:
    return when.strftime("%Y-%m-%d %H:%M:%S UTC")


@st.cache_data(ttl=3600, show_spinner="Loading cards...")
def load_minions(prefer_cache: bool) -> tuple[pd.DataFrame, str, str]:
    """Returns (minions, label, warning): where the data came from and when, plus a warning if
    we had to fall back (empty otherwise).

    Live is the default. If the live fetch fails we fall back to the cached file rather than erroring.
    The timestamp is taken at fetch time, so for live data it stays fixed while this result is held
    in Streamlit's cache.
    """
    fallback_reason = ""
    if not prefer_cache:
        try:
            fetched_at = datetime.now(timezone.utc)
            cards = json.loads(fetch_live_bytes())
            return normalize(cards), f"Live data fetched {fmt_utc(fetched_at)}", ""
        except (OSError, ValueError) as err:  # URLError/HTTPError/timeouts are OSErrors
            fallback_reason = f"Live data is unavailable ({err})."
    try:
        cards, fetched_at = read_latest_cache()
    except (OSError, ValueError, KeyError) as err:
        raise RuntimeError(f"{fallback_reason or 'Cached data was requested'} and the cache in {CACHE_DIR} "
                           f"could not be read ({err}). Run `python update_cache.py` while online.") from err
    label = f"Cached data from {fmt_utc(fetched_at)}"
    return normalize(cards), label, (f"{fallback_reason} Using the cached copy instead." if fallback_reason else "")


def options_for(df: pd.DataFrame, col: str) -> list[str]:
    """Dropdown values for a list column, ordered like hearthstone.html."""
    values = sorted({v for vals in df[col] for v in vals})
    has_none = bool((df[col].map(len) == 0).any())
    if col == "mechanics":
        public = [v for v in values if v in PUBLIC_MECHANICS]
        internal = [v for v in values if v not in PUBLIC_MECHANICS]
        return (["None"] if has_none else []) + public + ([SEPARATOR] if public and internal else []) + internal
    if col == "sets":
        # Roughly chronological: order sets by their lowest card database id.
        first = df.explode(col).groupby(col)["dbfId"].min()
        values.sort(key=first.get)
    return values + (["None"] if has_none else [])


def filter_by(df: pd.DataFrame, col: str, wanted: str) -> pd.DataFrame:
    if wanted in ("All", SEPARATOR):
        return df
    if wanted == "None":
        return df[df[col].map(len) == 0]
    # "ALL" (e.g. Amalgams) counts as every tribe.
    return df[df[col].map(lambda v: wanted in v or (col == "races" and "ALL" in v))]


def make_slots(values, collapse: bool) -> list[tuple[str, int | None]]:
    """Axis slots as (tick label, stat value). Value is None for a collapsed run of empty values.

    Always starts at 0. With `collapse`, runs of 2+ missing values between populated ones become one
    blank slot (e.g. 10, 11, "12-15", 16); a single missing value is still shown as its own slot.
    """
    present = sorted({0, *map(int, values)})
    slots, prev = [], None
    for v in present:
        if prev is not None and v - prev > 1:
            lo, hi = prev + 1, v - 1
            if collapse and hi > lo:
                slots.append((f"{lo}..{hi}", None))
            else:
                slots.extend((str(i), i) for i in range(lo, hi + 1))
        slots.append((str(v), v))
        prev = v
    return slots


def readable_text_color(t: float) -> str:
    """Black or white, whichever contrasts more with the heatmap color at position t (0-1).

    Uses WCAG relative luminance and contrast ratio. Picking the better of black/white always
    reaches at least ~4.6:1 (WCAG AA), unlike a fixed threshold on t, which fails in the middle of
    the scale where the color is neither clearly dark nor clearly light.
    """
    r, g, b = pc.unlabel_rgb(pc.sample_colorscale(COLORSCALE, [float(t)])[0])
    lin = [(c / 255 / 12.92) if c / 255 <= 0.03928 else ((c / 255 + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    lum = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    return "white" if 1.05 / (lum + 0.05) > (lum + 0.05) / 0.05 else "black"


def build_heatmap(df: pd.DataFrame, x: str, y: str, collapse: bool):
    """Returns the figure plus position -> stat value lookups for each axis (for click handling)."""
    xslots, yslots = make_slots(df[x], collapse), make_slots(df[y], collapse)
    xpos = {v: i for i, (_, v) in enumerate(xslots) if v is not None}
    ypos = {v: i for i, (_, v) in enumerate(yslots) if v is not None}

    z = np.zeros((len(yslots), len(xslots)), dtype=int)
    names = [[[] for _ in xslots] for _ in yslots]
    by_name = df.sort_values("name", kind="stable")
    for name, xv, yv in zip(by_name["name"], by_name[x], by_name[y]):
        z[ypos[yv], xpos[xv]] += 1
        names[ypos[yv]][xpos[xv]].append(name)

    def hover(r, c):
        cell = names[r][c]
        if not cell:
            return ""
        shown = "<br>".join(cell[:MAX_HOVER_NAMES])
        more = f"<br>...and {len(cell) - MAX_HOVER_NAMES} more" if len(cell) > MAX_HOVER_NAMES else ""
        return f"<b>{AXES[x]}: {xslots[c][0]}, {AXES[y]}: {yslots[r][0]}</b> ({len(cell)})<br>{shown}{more}"

    text = [[hover(r, c) for c in range(len(xslots))] for r in range(len(yslots))]
    zlog = np.log1p(z)  # log scale (as in the HTML) so a few huge cells don't wash out the rest
    fig = go.Figure(go.Heatmap(
        z=zlog, text=text, hovertemplate="%{text}<extra></extra>",
        colorscale=COLORSCALE, zmin=0, zmax=float(zlog.max()), showscale=False, xgap=1, ygap=1,
    ))
    # Heatmaps don't report clicks to Streamlit, so overlay an invisible scatter trace for selection.
    rows, cols = np.nonzero(z)
    fig.add_trace(go.Scatter(
        x=cols, y=rows, mode="markers+text", text=z[rows, cols].astype(str),
        textfont=dict(size=12, color=[readable_text_color(zlog[r, c] / zlog.max()) for r, c in zip(rows, cols)]),
        marker=dict(size=28, opacity=0), hoverinfo="skip", showlegend=False,
        selected=dict(marker=dict(opacity=0.25, color="#e6a700")),
        unselected=dict(marker=dict(opacity=0)),
    ))
    # Positions are slot indices, so label them with the real stat values. Axis ranges are pinned
    # so the first slot (0) sits at the origin. Don't set `scaleanchor`: forcing equal x/y scales
    # makes Plotly widen one axis symmetrically around the data, which pushed 0 to the middle.
    fig.update_layout(
        xaxis=dict(title=AXES[x], tickvals=list(range(len(xslots))), ticktext=[l for l, _ in xslots],
                   range=[-0.5, len(xslots) - 0.5], constrain="domain"),
        yaxis=dict(title=AXES[y], tickvals=list(range(len(yslots))), ticktext=[l for l, _ in yslots],
                   range=[-0.5, len(yslots) - 0.5], constrain="domain"),
        margin=dict(l=10, r=10, t=10, b=10), height=max(900, 40 * len(yslots) + 150), dragmode="select",
    )
    return fig, [v for _, v in xslots], [v for _, v in yslots]


def wiki_url(name: str) -> str:
    return "https://hearthstone.wiki.gg/wiki/" + urllib.parse.quote(name.replace(" ", "_"))


def main():
    st.set_page_config(page_title="Hearthstone Card Stat Correlations", layout="wide")
    st.title("Hearthstone Card Stat Correlations")
    with st.sidebar:
        st.header("Data")
        source = st.radio("Card data", ["Live (HearthstoneJSON)", "Cached copy"], index=0,
                          help="Live is the default; the cached copy is used automatically if live is unavailable.")
    minions, data_label, warning = load_minions(prefer_cache=source.startswith("Cached"))
    if warning:
        st.warning(warning)

    with st.sidebar:
        st.header("Axes")
        x = st.selectbox("X-axis", list(AXES), format_func=AXES.get, index=0)
        y = st.selectbox("Y-axis", list(AXES), format_func=AXES.get, index=1)

        st.header("Filters")
        picks = {
            col: st.selectbox(label, ["All"] + options_for(minions, col))
            for col, label in [("races", "Minion type / tribe"), ("classes", "Player class"),
                               ("sets", "Card set"), ("mechanics", "Mechanic")]
        }
        lo, hi = int(minions["total"].min()), int(minions["total"].max())
        collapse = st.checkbox("Collapse empty stretches on the axes", value=True,
                               help="Show a run of unpopulated values (e.g. 12-15) as one blank slot.")
        total_range = st.slider("Stat total", lo, hi, (lo, hi))

    df = minions[minions["total"].between(*total_range)]
    for col, wanted in picks.items():
        df = filter_by(df, col, wanted)

    st.caption(f"{len(df)} of {len(minions)} collectible minions match \u00b7 {data_label}")
    if df.empty:
        st.warning("No minions match these filters.")
        return

    fig, xvals, yvals = build_heatmap(df, x, y, collapse)
    event = st.plotly_chart(fig, on_select="rerun", selection_mode=("points", "box"),
                            key="heatmap", width="stretch")

    # Cells chosen by clicking (or box-selecting) the grid.
    # Selected points carry slot positions; translate back to stat values (None = collapsed blank slot).
    cells = {(xvals[int(p["x"])], yvals[int(p["y"])]) for p in event.selection.points}
    if not cells:
        st.info("Click a cell (or box-select several) to list its minions.")
        return
    picked = df[[(a, b) in cells for a, b in zip(df[x], df[y])]].sort_values("name")
    st.subheader(f"{len(picked)} minions in {len(cells)} selected cell{'s' if len(cells) != 1 else ''}")
    table = pd.DataFrame({
        "Name": picked["name"], "Cost": picked["cost"], "Attack": picked["attack"], "Health": picked["health"],
        "Tribe": picked["races"].map(", ".join), "Class": picked["classes"].map(", ".join),
        "Set": picked["sets"].map(", ".join), "Wiki": picked["name"].map(wiki_url),
    })
    st.dataframe(table, hide_index=True, width="stretch",
                 column_config={"Wiki": st.column_config.LinkColumn("Wiki", display_text="open")})


if __name__ == "__main__":  # `streamlit run` executes the script as __main__
    main()
