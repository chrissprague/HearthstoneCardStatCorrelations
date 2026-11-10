# HearthstoneCardStatCorrelations
A fork of [Yawar Raza](https://github.com/YawarRaza7349)'s **[YuGiOhCardStatCorrelations](https://github.com/YawarRaza7349/YuGiOhCardStatCorrelations)** used to visualize card stats in a graph. For the more intricate details, visit his repository. He wrote virtually all of the important code - I just wrote the stuff to make it work with Hearthstone cards.

Card data is fetched live from the [HearthstoneJSON](https://hearthstonejson.com/) API (`api.hearthstonejson.com/v1/latest/enUS/cards.collectible.json`), so it stays current without updating a cached file. It needs an internet connection. Only collectible minions are shown, and minions with multiple tribes (or multiple classes) are matched under each one.

## Streamlit app (recommended)
`hearthstone_app.py` is a pandas + Plotly + Streamlit app: a heatmap of how many minions share each pair of stat values, with filters and a card listing.

### Setup
Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run
```bash
streamlit run hearthstone_app.py
```
Streamlit prints a local URL (normally http://localhost:8501) and opens it in your browser. The card data is downloaded once and kept in memory for an hour, so changing filters doesn't re-fetch it.

### Live vs cached data
The app uses live API data by default. If the API can't be reached, it automatically falls back to a cached copy committed at `data/minions_cache.json` and shows a warning with the date of that copy. You can also pick "Cached copy" under **Data** in the sidebar to use it deliberately (for example, offline).

The cache holds only minions and only the fields the app uses (about 850 KB). To refresh it while online:
```bash
python update_cache.py
```

### Using it
- **Axes (sidebar):** pick the X and Y stats: attack, health, mana cost, or stat total (attack + health). Darker blue cells hold more minions (log-scaled, so a few crowded cells don't wash out the rest), and each cell shows its count.
- **Filters (sidebar):** minion type / tribe, player class, card set, mechanic, and a stat total range. "None" selects minions with no value for that field. Selecting a tribe also includes minions that are every tribe (e.g. Amalgams). Sets are listed in release order. Mechanics list player-facing keywords first, then a separator, then internal tags.
- **Collapse empty stretches (sidebar):** on by default. Runs of unused values (e.g. 12 to 15) show as one blank column or row labeled with the range, so rare outliers don't stretch the chart. Turn it off for true proportions.
- **Hover** a cell to see the minions in it.
- **Box-select** (drag over cells) to list the minions in the selected cells below the chart, with their stats, tribe, class, set and a link to the card's [Hearthstone wiki](https://hearthstone.wiki.gg/) page. Single-click selection currently doesn't work; use box-select, which also works on a single cell.

When new keywords or sets are added, the public keyword list in the app (`PUBLIC_MECHANICS`) may need updating from the [wiki's Keywords category](https://hearthstone.wiki.gg/wiki/Category:Keywords). Until then, a new keyword shows up below the separator in the mechanic dropdown.

## Original HTML versions
These are static pages with no install step.

- **`hearthstone.html`** is the original Hearthstone grid, with the same live API data as above. Open it directly in a browser (double-click it, or `xdg-open hearthstone.html`). It has dropdowns for the X and Y axes (attack, health, mana cost), tribe, class, card set and mechanic. Click a cell to list its minions, each linking to its wiki page. Cells are grayscale, darker for more cards.
- **`index.html`** is the original Yu-Gi-Oh! version from the upstream repository. It reads its card data from the bundled `not_json.js` and is unrelated to Hearthstone. Open it directly in a browser.
