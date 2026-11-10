# HearthstoneCardStatCorrelations
A fork of [Yawar Raza](https://github.com/YawarRaza7349)'s **[YuGiOhCardStatCorrelations](https://github.com/YawarRaza7349/YuGiOhCardStatCorrelations)** used to visualize card stats in a graph. For the more intricate details, visit his repository. He wrote virtually all of the important code - I just wrote the stuff to make it work with Hearthstone cards.

Card data is fetched live from the [HearthstoneJSON](https://hearthstonejson.com/) API (`api.hearthstonejson.com/v1/latest/enUS/cards.collectible.json`). Cached versions may also be available under `data` when running without an internet connection.

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
Streamlit prints a local URL (normally http://localhost:8501) and opens it in your browser.

## Original HTML versions
These are static pages with no install step.

- **`hearthstone.html`** is the original Hearthstone grid, with the same live API data as above. Open it directly in a browser (double-click it, or `xdg-open hearthstone.html`).
- **`index.html`** is the original Yu-Gi-Oh! version from the upstream repository. It reads its card data from the bundled `not_json.js` and is unrelated to Hearthstone. Open it directly in a browser.
