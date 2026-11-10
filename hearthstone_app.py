"""Streamlit + Plotly port of hearthstone.html.

A heatmap of how many collectible minions share each pair of stat values, with
filters on tribe / class / set / mechanic / stat total. Click a cell to list the
minions in it, with links to their wiki pages.

    pip install -r requirements.txt
    streamlit run hearthstone_app.py
"""
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

CARDS_URL = "https://api.hearthstonejson.com/v1/latest/enUS/cards.collectible.json"

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

AXES = {"attack": "Attack", "health": "Health", "cost": "Mana cost", "total": "Stat total (atk + hp)"}
SEPARATOR = "────────"
MAX_HOVER_NAMES = 12


@st.cache_data(ttl=3600, show_spinner="Fetching cards from HearthstoneJSON...")
def load_minions() -> pd.DataFrame:
    """Fetch collectible cards and normalize to one row per minion (list-valued tag columns)."""
    # Send our own User-Agent in case the API's CDN rejects urllib's default one.
    req = urllib.request.Request(CARDS_URL, headers={"User-Agent": "hearthstone-card-stat-correlations"})
    with urllib.request.urlopen(req) as resp:
        cards = pd.read_json(resp)

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


def build_heatmap(df: pd.DataFrame, x: str, y: str) -> go.Figure:
    # Count over the full integer range so no values are skipped, then reindex to fill gaps with 0.
    xs = list(range(0, int(df[x].max()) + 1))
    ys = list(range(0, int(df[y].max()) + 1))
    counts = pd.crosstab(df[y], df[x]).reindex(index=ys, columns=xs, fill_value=0)

    # Names per cell for the hover text.
    names = df.sort_values("name").groupby([y, x])["name"].apply(list)

    def hover(yv, xv):
        cell = names.get((yv, xv), [])
        if not cell:
            return ""
        shown = "<br>".join(cell[:MAX_HOVER_NAMES])
        more = f"<br>...and {len(cell) - MAX_HOVER_NAMES} more" if len(cell) > MAX_HOVER_NAMES else ""
        return f"<b>{AXES[x]}: {xv}, {AXES[y]}: {yv}</b> ({len(cell)})<br>{shown}{more}"

    text = [[hover(yv, xv) for xv in xs] for yv in ys]
    z = counts.to_numpy()
    # Log scale (as in the HTML) so a few huge cells don't wash out the rest; plain counts shown as labels.
    fig = go.Figure(go.Heatmap(
        x=xs, y=ys, z=np.log1p(z), text=text, hovertemplate="%{text}<extra></extra>",
        colorscale=[[0, "white"], [1, "black"]], showscale=False, xgap=1, ygap=1,
    ))
    # Heatmaps don't report clicks to Streamlit, so overlay an invisible scatter trace for selection.
    gx, gy = np.meshgrid(xs, ys)
    nonzero = z > 0
    fig.add_trace(go.Scatter(
        x=gx[nonzero], y=gy[nonzero], mode="markers+text", text=z[nonzero].astype(str),
        textfont=dict(size=10, color=["white" if v > 0.5 * np.log1p(z.max()) else "black"
                                      for v in np.log1p(z[nonzero])]),
        marker=dict(size=28, opacity=0), hoverinfo="skip", showlegend=False,
        selected=dict(marker=dict(opacity=0.25, color="#e6a700")),
        unselected=dict(marker=dict(opacity=0)),
    ))
    fig.update_layout(
        xaxis=dict(title=AXES[x], dtick=1, range=[-0.5, xs[-1] + 0.5]),
        yaxis=dict(title=AXES[y], dtick=1, range=[-0.5, ys[-1] + 0.5], scaleanchor="x"),
        margin=dict(l=10, r=10, t=10, b=10), height=620, dragmode="select",
    )
    return fig


def wiki_url(name: str) -> str:
    return "https://hearthstone.wiki.gg/wiki/" + urllib.parse.quote(name.replace(" ", "_"))


def main():
    st.set_page_config(page_title="Hearthstone Card Stat Correlations", layout="wide")
    st.title("Hearthstone Card Stat Correlations")
    minions = load_minions()

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
        total_range = st.slider("Stat total (atk + hp)", lo, hi, (lo, hi))

    df = minions[minions["total"].between(*total_range)]
    for col, wanted in picks.items():
        df = filter_by(df, col, wanted)

    st.caption(f"{len(df)} of {len(minions)} collectible minions match")
    if df.empty:
        st.warning("No minions match these filters.")
        return

    fig = build_heatmap(df, x, y)
    event = st.plotly_chart(fig, on_select="rerun", selection_mode=("points", "box"),
                            key="heatmap", width="stretch")

    # Cells chosen by clicking (or box-selecting) the grid.
    cells = {(int(p["x"]), int(p["y"])) for p in event.selection.points}
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


main()
