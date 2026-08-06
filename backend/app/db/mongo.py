"""
MongoDB (Motor async) — market history, AI reasoning, news, conversations,
watchlists. Vector embeddings live in ChromaDB (see db/chroma.py); Mongo holds
the document/reasoning records the dashboard reads.
"""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    return _client


def get_mongo() -> AsyncIOMotorDatabase:
    return get_client()[settings.MONGO_DB]


# ---- collection shortcuts (single source of names) ----
COLLECTIONS = {
    "analyses": "analyses",          # AI reasoning + final decisions per run
    "market": "market_history",      # OHLCV / quotes snapshots
    "news": "news",                  # collected + summarized articles
    "conversations": "conversations",  # AI chat history (with memory)
    "signals": "signals",            # generated recommendations feed
    "watchlist": "watchlist",        # tickers the user tracks (server-side, so
                                      # the scheduled dataset job can read it)
    "scheduler_state": "scheduler_state",  # last-run bookkeeping for periodic jobs
    "paper_portfolio": "paper_portfolio",  # simulated paper-trading positions/cash
    "paper_trades": "paper_trades",  # simulated paper-trading trade log
}


def coll(name: str):
    return get_mongo()[COLLECTIONS.get(name, name)]


async def init_mongo() -> None:
    """Create indexes idempotently on startup."""
    db = get_mongo()
    try:
        await db[COLLECTIONS["analyses"]].create_index(
            [("ticker", 1), ("created_at", -1)]
        )
        await db[COLLECTIONS["market"]].create_index(
            [("ticker", 1), ("date", -1)]
        )
        await db[COLLECTIONS["news"]].create_index([("published_at", -1)])
        await db[COLLECTIONS["news"]].create_index([("tickers", 1)])
        await db[COLLECTIONS["conversations"]].create_index(
            [("user_id", 1), ("updated_at", -1)]
        )
        await db[COLLECTIONS["signals"]].create_index(
            [("ticker", 1), ("created_at", -1)]
        )
        await db[COLLECTIONS["watchlist"]].create_index([("ticker", 1)], unique=True)
        await db[COLLECTIONS["paper_trades"]].create_index(
            [("ticker", 1), ("created_at", -1)]
        )
        log.info("MongoDB ready (indexes ensured)")
    except Exception as e:  # noqa: BLE001
        log.warning("MongoDB index init failed (will retry lazily): %s", e)


async def ping_mongo() -> bool:
    try:
        await get_client().admin.command("ping")
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("MongoDB ping failed: %s", e)
        return False


def serialize(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert Mongo _id/ObjectId to a JSON-safe string id."""
    if not doc:
        return doc
    out = dict(doc)
    _id = out.pop("_id", None)
    if _id is not None:
        out["id"] = str(_id)
    return out
