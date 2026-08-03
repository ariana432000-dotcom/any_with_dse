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
async def news(ticker: str, limit: int = Query(8, ge=1, le=30), refresh: bool = Query(False)) -> dict:
    return {"ticker": ticker.upper(), "items": await mds.get_news(ticker, limit, refresh=refresh)}
