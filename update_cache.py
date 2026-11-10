"""Refresh the offline card cache used when the live API is unavailable.

    python update_cache.py
"""
from hearthstone_app import CACHE_PATH, fetch_live_cards, write_cache

if __name__ == "__main__":
    count = write_cache(fetch_live_cards())
    print(f"Wrote {count} minions to {CACHE_PATH}")
