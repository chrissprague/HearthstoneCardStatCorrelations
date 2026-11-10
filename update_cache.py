"""Save a fresh copy of the live API response as the offline cache.

    python update_cache.py

The response is stored untouched as data/cards.collectible_<fetch time>.json. Older cache files are
left in place; the app uses the newest one.
"""
from datetime import datetime, timezone

from hearthstone_app import fetch_live_bytes, write_cache

if __name__ == "__main__":
    fetched_at = datetime.now(timezone.utc)
    path = write_cache(fetch_live_bytes(), fetched_at)
    print(f"Wrote {path} ({path.stat().st_size / 1e6:.1f} MB)")
