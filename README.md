# HearthstoneCardStatCorrelations
A fork of [Yawar Raza](https://github.com/YawarRaza7349)'s **[YuGiOhCardStatCorrelations](https://github.com/YawarRaza7349/YuGiOhCardStatCorrelations)** used to visualize card stats in a graph. For the more intricate details, visit his repository. He wrote virtually all of the important code - I just wrote the stuff to make it work with Hearthstone cards.

Card data is fetched live from the [HearthstoneJSON](https://hearthstonejson.com/) API (`api.hearthstonejson.com/v1/latest/enUS/cards.collectible.json`), so it stays current without updating a cached file. Minions with multiple tribes are matched under each tribe.
