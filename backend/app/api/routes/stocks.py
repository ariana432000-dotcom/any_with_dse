"""Stock market-data routes — live (keyless Yahoo/Stooq) by default."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.services import market_data as mds

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/{ticker}/quote")
async def quote(ticker: str) -> dict:
    return await mds.get_quote(ticker)


@router.get("/{ticker}/history")
async def history(ticker: str, days: int = Query(220, ge=5, le=2000)) -> dict:
    return await mds.get_history(ticker, days_back=days)


@router.get("/{ticker}/news")
async def news(ticker: str, limit: int = Query(8, ge=1, le=30)) -> dict:
    return {"ticker": ticker.upper(), "items": await mds.get_news(ticker, limit)}


@router.get("/{ticker}/news/debug")
async def news_debug(ticker: str, limit: int = Query(8, ge=1, le=30)) -> dict:
    """Uncached diagnostics for the DSE news path -- per-source hit counts
    and, when a ticker had zero sharenews24 matches, a sample of the
    cached article titles it was checked against. Lets you see WHY a
    ticker got fewer/no sharenews24 results without digging through
    Railway's Deploy Logs."""
    import asyncio

    return await asyncio.to_thread(mds.get_news_debug, ticker, limit)
