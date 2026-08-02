"""
Watchlist store — Mongo persistence for the tickers the user tracks.

Previously the watchlist lived ONLY in the browser's localStorage, which meant
the backend (and any server-side scheduled job, like the daily dataset export)
had no way to know which tickers to track. This is now the single source of
truth; the frontend still keeps a localStorage cache for instant paint /
offline fallback, but syncs through this store on every add/remove.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import settings
from app.core.logging import get_logger
from app.db import mongo as _mongo

log = get_logger(__name__)

_COLL = "watchlist"


def _db():
    return _mongo.get_mongo()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WatchlistStore:
    @staticmethod
    async def list_tickers() -> list[str]:
        """Returns tickers in insertion order. Seeds from the configured
        default watchlist the first time it's ever called (empty collection),
        so a fresh install isn't an empty dashboard."""
        try:
            cur = _db()[_COLL].find().sort("added_at", 1)
            docs = await cur.to_list(length=500)
        except Exception as e:  # noqa: BLE001
            log.warning("watchlist list failed, falling back to configured default: %s", e)
            return list(settings.watch_tickers)

        if not docs:
            seeded = settings.watch_tickers
            for t in seeded:
                await WatchlistStore.add(t)
            return list(seeded)

        return [d["_id"] for d in docs]

    @staticmethod
    async def add(ticker: str) -> list[str]:
        t = ticker.strip().upper()
        if not t:
            return await WatchlistStore.list_tickers()
        try:
            await _db()[_COLL].update_one(
                {"_id": t},
                {"$setOnInsert": {"ticker": t, "added_at": _now()}},
                upsert=True,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("watchlist add failed for %s: %s", t, e)
        return await WatchlistStore.list_tickers()

    @staticmethod
    async def remove(ticker: str) -> list[str]:
        t = ticker.strip().upper()
        try:
            await _db()[_COLL].delete_one({"_id": t})
        except Exception as e:  # noqa: BLE001
            log.warning("watchlist remove failed for %s: %s", t, e)
        return await WatchlistStore.list_tickers()
