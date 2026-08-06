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
    """🔴 FIXED: app/api/routes/stocks.py's news route already calls this
    as get_news(ticker, limit, refresh=refresh) -- without `refresh`
    accepted here, every /news request raised TypeError: get_news() got
    an unexpected keyword argument 'refresh', a 500 on every single call.
    `refresh=True` skips the cache read (still writes a fresh entry after),
    for testing/debugging without waiting out the 10-minute TTL below."""
    key = f"news:{ticker.upper()}:{limit}"
    if not refresh:
        cached = await _cache_get(key)
        if cached:
            return cached
    items = await asyncio.to_thread(md.fetch_recent_news, ticker, limit)
    await _cache_set(key, items, ttl=600)
    return items


def get_news_debug(ticker: str, limit: int = 8) -> dict:
    """🔴 FIXED: /api/stocks/{ticker}/news/debug (routes/stocks.py) has
    been calling this function since it was added, but it was never
    actually defined here -- every call raised AttributeError. Runs the
    same DSE news fetch as get_news() but with a debug_sink attached, so
    the per-source match counts and "sample titles (no match found)" log
    lines are returned directly instead of only existing in Railway's
    Deploy Logs. Synchronous/blocking (network calls) -- routes/stocks.py
    already runs it via asyncio.to_thread.
    """
    ticker = ticker.upper()
    from tradingagents.dataflows.symbol_utils import is_dse_ticker
    if not is_dse_ticker(ticker):
        return {
            "ticker": ticker,
            "items": md.fetch_recent_news(ticker, limit),
            "logs": ["Not a DSE ticker -- this uses Google News RSS, which has no debug_sink."],
        }
    debug_sink: list[str] = []
    items = md._fetch_dse_news(ticker, limit, debug_sink=debug_sink)
    return {"ticker": ticker, "items": items, "logs": debug_sink}


async def get_fundamentals_check(ticker: str) -> dict:
    """Standalone fundamentals sanity-check for the "Fundamentals Check"
    UI page -- a single HTTP fetch to the vendor (dsebd.org for DSE
    tickers), no LLM calls, no other analysts, no full LangGraph pipeline.
    Lets you verify a scrape/parsing fix in a couple seconds instead of
    running a full (slow) AI Analysis pass just to see one field."""
    ticker = ticker.upper()
    from tradingagents.dataflows.symbol_utils import is_dse_ticker
    if not is_dse_ticker(ticker):
        return {
            "ticker": ticker,
            "ok": None,
            "status": (
                "Not a recognized DSE trading code -- the Fundamentals Check "
                "tool currently only covers dsebd.org-listed tickers."
            ),
            "parsed": {},
            "raw_response": "",
        }
    from tradingagents.dataflows import dse_fundamentals
    curr_date = datetime.now().strftime("%Y-%m-%d")
    return await asyncio.to_thread(dse_fundamentals.quick_check, ticker, curr_date)
<<<<<<< HEAD


# ✅ ADDED — backs the new PDF-upload feature (app/api/routes/stocks.py's
# POST /{ticker}/reports/upload and GET /{ticker}/reports). Writes straight
# into dse_statement_extractor.py's own REPORTS_DIR/CACHE_DIR so a file
# uploaded here is picked up by get_balance_sheet/get_cashflow/
# get_income_statement (called from create_fundamentals_analyst in
# app/pipeline/agents.py) with no other wiring needed.
def _reports_dir():
    from tradingagents.dataflows.dse_statement_extractor import REPORTS_DIR
    return REPORTS_DIR


def _cache_path(ticker: str):
    from tradingagents.dataflows.dse_statement_extractor import _cache_path as cp
    return cp(ticker)


async def save_dse_report(ticker: str, fiscal_year: str, pdf_bytes: bytes) -> str:
    import re as _re

    def _write():
        # fiscal_year becomes a filename (see dse_statement_extractor.py's
        # get_statement: pdf_path.stem IS the fiscal_year key) -- reject
        # anything that isn't safe as one, rather than silently mangling
        # a user-entered value like "2024/2025" into a nested path.
        safe_fy = _re.sub(r"[^A-Za-z0-9_-]", "", fiscal_year)
        if not safe_fy:
            raise ValueError("fiscal_year must contain at least one letter/digit")
        ticker_dir = _reports_dir() / ticker
        ticker_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = ticker_dir / f"{safe_fy}.pdf"
        pdf_path.write_bytes(pdf_bytes)
        # Re-uploading the same ticker/fiscal_year should re-extract, not
        # keep serving whatever was cached from a previous (possibly bad)
        # upload -- drop just that one cached year rather than the whole
        # per-ticker cache file.
        cache_file = _cache_path(ticker)
        if cache_file.exists():
            import json
            try:
                cache = json.loads(cache_file.read_text())
            except Exception:  # noqa: BLE001
                cache = {}
            if safe_fy in cache:
                del cache[safe_fy]
                cache_file.write_text(json.dumps(cache, indent=2))
        return str(pdf_path)

    return await asyncio.to_thread(_write)


async def list_dse_reports(ticker: str) -> dict:
    def _list():
        ticker_dir = _reports_dir() / ticker
        pdfs = sorted(p.stem for p in ticker_dir.glob("*.pdf")) if ticker_dir.exists() else []
        cache_file = _cache_path(ticker)
        extracted = []
        if cache_file.exists():
            import json
            try:
                extracted = sorted(json.loads(cache_file.read_text()).keys())
            except Exception:  # noqa: BLE001
                pass
        return {
            "ticker": ticker,
            "uploaded_fiscal_years": pdfs,
            "extracted_fiscal_years": extracted,
            "pending_extraction": sorted(set(pdfs) - set(extracted)),
        }

    return await asyncio.to_thread(_list)
=======
>>>>>>> ade75414b6567b17d70c76d7f1b7d5363ff039b5
