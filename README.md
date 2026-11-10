# HearthstoneCardStatCorrelations
A fork of [Yawar Raza](https://github.com/YawarRaza7349)'s **[YuGiOhCardStatCorrelations](https://github.com/YawarRaza7349/YuGiOhCardStatCorrelations)** used to visualize card stats in a graph. For the more intricate details, visit his repository. He wrote virtually all of the important code - I just wrote the stuff to make it work with Hearthstone cards.

Card data is fetched live from the [HearthstoneJSON](https://hearthstonejson.com/) API (`api.hearthstonejson.com/v1/latest/enUS/cards.collectible.json`), so it stays current without updating a cached file. Minions with multiple tribes are matched under each tribe.

## Streamlit version
`hearthstone_app.py` is a Python port (pandas + Plotly + Streamlit) with the same filters, plus a stat-total (attack + health) axis and filter. Click or box-select cells in the grid to list their minions with wiki links.

```
pip install -r requirements.txt
streamlit run hearthstone_app.py
```
