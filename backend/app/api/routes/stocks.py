"""
Market-data service — a provider-agnostic facade.

Yahoo/Stooq work keyless out of the box (via the ported pipeline helper). Other
providers (Finnhub, Polygon, AlphaVantage, TwelveData, FMP) are pluggable: add a
fetch function keyed by name and set DEFAULT_MARKET_PROVIDER / pass provider=.
Results are cached in Redis and snapshotted into MongoDB for the dashboard.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from app.core.config import settings
from app.core.logging import get_logger
from app.db.mongo import coll
from app.db.redis_client import get_redis
from app.pipeline import market_data as md

log = get_logger(__name__)

_CACHE_TTL = 120  # seconds for quote/history cache


async def _cache_get(key: str):
    try:
        raw = await get_redis().get(key)
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001
        return None


async def _cache_set(key: str, value, ttl: int = _CACHE_TTL):
    try:
        await get_redis().set(key, json.dumps(value), ex=ttl)
    except Exception:  # noqa: BLE001
        pass


async def get_history(ticker: str, days_back: int = 220, asset_type: str = "stock") -> dict:
    """OHLCV history + computed indicators. Cached; persisted to Mongo."""
    ticker = ticker.upper()
    key = f"hist:{ticker}:{days_back}"
    cached = await _cache_get(key)
    if cached:
        return cached

    end = datetime.now().strftime("%Y-%m-%d")
    start, end = md.window_dates(end, days_back=days_back)
    # md.fetch_ohlcv is blocking (network); run it off the event loop.
    rows = await asyncio.to_thread(md.fetch_ohlcv, ticker, start, end, asset_type)
    indicators = md.compute_indicators(rows) if rows else {}
    result = {
        "ticker": ticker,
        "rows": rows,
        "indicators": indicators,
        "latest_close": md.latest_close(rows),
        "provider": settings.DEFAULT_MARKET_PROVIDER,
        "fetched_at": datetime.utcnow().isoformat(),
    }
    await _cache_set(key, result)

    # Snapshot latest bar to Mongo (best-effort).
    try:
        if rows:
            last = rows[-1]
            await coll("market").update_one(
                {"ticker": ticker, "date": last["date"]},
                {"$set": {**last, "ticker": ticker, "indicators": indicators}},
                upsert=True,
            )
    except Exception as e:  # noqa: BLE001
        log.debug("market snapshot skipped: %s", e)

    return result


async def get_quote(ticker: str) -> dict:
    """Lightweight latest-price view derived from history."""
    hist = await get_history(ticker, days_back=10)
    rows = hist.get("rows") or []
    if not rows:
        return {"ticker": ticker.upper(), "price": None, "change_pct": None}
    last = rows[-1]
    prev = rows[-2] if len(rows) > 1 else last
    change = None
    try:
        if prev["close"]:
            change = (last["close"] - prev["close"]) / prev["close"] * 100
    except Exception:  # noqa: BLE001
        change = None
    return {
        "ticker": ticker.upper(),
        "price": last.get("close"),
        "open": last.get("open"),
        "high": last.get("high"),
        "low": last.get("low"),
        "volume": last.get("volume"),
        "change_pct": round(change, 2) if change is not None else None,
        "date": last.get("date"),
    }


async def get_news(ticker: str, limit: int = 8, refresh: bool = False) -> list[dict]:
    """✅ CHANGED: restored `refresh` -- without it, the 10-minute cache
    below made every news-fetching code change look like a no-op for up to
    10 minutes after each deploy. `refresh=True` skips the cache read
    (still writes a fresh entry after), for testing/debugging."""
    key = f"news:{ticker.upper()}:{limit}"
    if not refresh:
        cached = await _cache_get(key)
        if cached:
            return cached
    items = await asyncio.to_thread(md.fetch_recent_news, ticker, limit)
    await _cache_set(key, items, ttl=600)
    return items


def get_news_debug(ticker: str, limit: int = 8) -> dict:
    """✅ CHANGED: this was called from app/api/routes/stocks.py's
    /{ticker}/news/debug route but was never actually defined here --
    that route would 500 on every call. Runs the DSE news path directly
    (bypassing the cache entirely, always fresh) and returns the same
    diagnostic lines _fetch_dse_news already logs via Deploy Logs, inline
    in the JSON response instead. Sync (not async) to match how stocks.py
    already calls this -- via asyncio.to_thread, same as get_news does
    internally for its own blocking fetch_recent_news call."""
    from app.pipeline.market_data import _fetch_dse_news
    debug_lines: list[str] = []
    items = _fetch_dse_news(ticker.upper(), limit, debug_lines)
    return {"ticker": ticker.upper(), "items": items, "debug": debug_lines}
