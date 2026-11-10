#!/usr/bin/env python3
"""Python/pandas/matplotlib equivalent of hearthstone.html.

Plots a grid of how many collectible minions share each pair of stat values
(attack / health / cost), optionally filtered by tribe, class, set or mechanic.

Examples:
    python hearthstone_correlations.py                         # attack (x) vs health (y)
    python hearthstone_correlations.py -x cost -y attack --race DRAGON
    python hearthstone_correlations.py --set TGT --mechanic TAUNT -o taunt.png
    python hearthstone_correlations.py --cell 3 4              # list minions at attack=3, health=4
    python hearthstone_correlations.py --list-values mechanics
"""
import argparse
import urllib.request

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

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

# Maps a filter name to the (normalized) list-valued column it filters on.
FILTERS = {"race": "races", "player_class": "classes", "set": "sets", "mechanic": "mechanics"}


def load_minions(url: str = CARDS_URL) -> pd.DataFrame:
    """Fetch the collectible cards and normalize them into one row per minion."""
    # Cloudflare in front of the API can reject urllib's default User-Agent, so send our own.
    req = urllib.request.Request(url, headers={"User-Agent": "hearthstone-card-stat-correlations"})
    with urllib.request.urlopen(req) as resp:
        cards = pd.read_json(resp)

    minions = cards[cards["type"] == "MINION"].copy()
    # Drop anything missing a stat (the JS version does the same).
    minions = minions.dropna(subset=["cost", "attack", "health"])
    minions[["cost", "attack", "health"]] = minions[["cost", "attack", "health"]].astype(int)

    # DISCUSSION: tribes. Cards can have several tribes, which the API exposes as a `races` list
    # (older cards also have a single `race`, kept for backwards compatibility - we ignore it
    # unless `races` is missing). Classes work the same way: multi-class cards have a `classes`
    # list and no `cardClass`. Rather than exploding to one row per (card, tribe) - which would
    # make a Dragon/Undead minion count twice in the *unfiltered* grid - we keep list-valued
    # columns and filter with membership tests. Each card therefore counts exactly once.
    def as_list(row_list, row_single):
        if isinstance(row_list, list) and row_list:
            return row_list
        if isinstance(row_single, str) and row_single:
            return [row_single]
        return []

    for col in ("races", "classes", "mechanics", "race", "cardClass"):
        if col not in minions:
            minions[col] = None
    minions["races"] = [as_list(a, b) for a, b in zip(minions["races"], minions["race"])]
    minions["classes"] = [as_list(a, b) for a, b in zip(minions["classes"], minions["cardClass"])]
    minions["mechanics"] = [m if isinstance(m, list) else [] for m in minions["mechanics"]]
    minions["sets"] = [[s] if isinstance(s, str) else [] for s in minions["set"]]
    return minions[["name", "dbfId", "cost", "attack", "health", "races", "classes", "sets", "mechanics"]]


def matches(values: list, wanted: str, is_race: bool) -> bool:
    if wanted == "None":
        return not values
    # "ALL" (e.g. Amalgams) counts as every tribe.
    return wanted in values or (is_race and "ALL" in values)


def apply_filters(df: pd.DataFrame, **selected) -> pd.DataFrame:
    for name, wanted in selected.items():
        if wanted is None:
            continue
        col = FILTERS[name]
        mask = df[col].map(lambda v: matches(v, wanted, col == "races"))
        df = df[mask]
    return df


def distinct_values(df: pd.DataFrame, col: str) -> list:
    """Dropdown-equivalent: possible values of a list column, ordered like the web UI."""
    values = sorted({v for vals in df[col] for v in vals})
    has_none = (df[col].map(len) == 0).any()
    if col == "mechanics":
        public = [v for v in values if v in PUBLIC_MECHANICS]
        internal = [v for v in values if v not in PUBLIC_MECHANICS]
        out = (["None"] if has_none else []) + public
        return out + (["--------"] + internal if public and internal else internal)
    if col == "sets":
        # Roughly chronological: order sets by their lowest card database id.
        first = {s: df.loc[df[col].map(lambda v, s=s: s in v), "dbfId"].min() for s in values}
        values.sort(key=first.get)
    return values + (["None"] if has_none else [])


def build_grid(df: pd.DataFrame, x: str, y: str) -> pd.DataFrame:
    """Count cards per (y, x), over the *full* integer range so no values are skipped."""
    # DISCUSSION: the JS builds nested dicts then walks min..max. pandas does this with a
    # crosstab + reindex, which also fills the gaps with 0. The minimum is 0 for all three
    # stats (the JS has a leftover "l" check from the Yu-Gi-Oh original that never fires here).
    grid = pd.crosstab(df[y], df[x])
    xs = range(0, int(df[x].max()) + 1)
    ys = range(0, int(df[y].max()) + 1)
    return grid.reindex(index=ys, columns=xs, fill_value=0)


def plot_grid(grid: pd.DataFrame, x: str, y: str, title: str):
    counts = grid.to_numpy()
    # DISCUSSION: darkness is log(1 + n) / log(1 + max) in the JS, to stop the few huge cells
    # (e.g. 2/3s) from washing out everything else. That is exactly matplotlib's gray_r with a
    # log-ish normalization applied by hand; we don't use LogNorm because it can't take 0.
    darkness = np.log1p(counts) / np.log1p(counts.max()) if counts.max() > 0 else counts
    fig, ax = plt.subplots(figsize=(0.45 * counts.shape[1] + 2, 0.45 * counts.shape[0] + 1.5))
    # origin="lower" puts (0, 0) at the bottom-left, as the JS does by reversing its rows.
    ax.imshow(darkness, cmap="gray_r", origin="lower", vmin=0, vmax=1)
    ax.set_xticks(range(counts.shape[1]), labels=grid.columns)
    ax.set_yticks(range(counts.shape[0]), labels=grid.index)
    ax.set_xlabel(x.capitalize() if x != "cost" else "Mana cost")
    ax.set_ylabel(y.capitalize() if y != "cost" else "Mana cost")
    ax.set_title(title)
    # DISCUSSION: the web page shows the count only through darkness + click-to-list. A static
    # image has no click, so we print the count in each non-empty cell instead (white text on
    # dark cells, black on light) and offer --cell to list the names.
    for (row, col), n in np.ndenumerate(counts):
        if n:
            ax.text(col, row, n, ha="center", va="center", fontsize=7,
                    color="white" if darkness[row, col] > 0.5 else "black")
    fig.tight_layout()
    return fig


def main():
    stats = ["attack", "health", "cost"]
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-x", choices=stats, default="attack", help="x-axis stat (default: attack)")
    p.add_argument("-y", choices=stats, default="health", help="y-axis stat (default: health)")
    p.add_argument("--race", help="tribe, e.g. BEAST (or None)")
    p.add_argument("--player-class", dest="player_class", help="class, e.g. MAGE (or None)")
    p.add_argument("--set", help="card set, e.g. TGT (or None)")
    p.add_argument("--mechanic", help="mechanic, e.g. TAUNT (or None)")
    p.add_argument("-o", "--output", help="save the plot to this file instead of showing it")
    p.add_argument("--cell", nargs=2, type=int, metavar=("X", "Y"),
                   help="print the minions at this x/y value (the 'click a cell' feature)")
    p.add_argument("--list-values", choices=list(FILTERS.values()),
                   help="print the possible values for a filter and exit")
    args = p.parse_args()

    minions = load_minions()
    if args.list_values:
        print("\n".join(distinct_values(minions, args.list_values)))
        return

    df = apply_filters(minions, race=args.race, player_class=args.player_class,
                       set=args.set, mechanic=args.mechanic)
    if df.empty:
        p.error("no minions match those filters")

    if args.cell:
        cx, cy = args.cell
        hit = df[(df[args.x] == cx) & (df[args.y] == cy)].sort_values("name")
        print(f"{args.x}: {cx}, {args.y}: {cy} ({len(hit)} minions)")
        for name in hit["name"]:
            print(f"  {name}  https://hearthstone.wiki.gg/wiki/{name.replace(' ', '_')}")
        return

    active = {k: v for k, v in vars(args).items() if k in FILTERS and v}
    title = f"{len(df)} minions" + (" (" + ", ".join(f"{k}={v}" for k, v in active.items()) + ")" if active else "")
    plot_grid(build_grid(df, args.x, args.y), args.x, args.y, title)
    if args.output:
        plt.savefig(args.output, dpi=150)
    else:
        plt.show()


if __name__ == "__main__":
    main()
