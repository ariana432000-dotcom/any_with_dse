"""Backtest / accuracy tracker API — aggregated win-rate & P&L stats over
RESOLVED RAEM episodes (see app/services/backtest.py).

    GET /backtest            aggregated across every ticker with history
    GET /backtest/{ticker}   aggregated for one ticker
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from app.services.backtest import compute_backtest

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("")
async def backtest_all(limit: int = Query(1000, ge=1, le=5000)) -> dict:
    # RAEMMemory/Chroma calls are synchronous — run off-thread so a slow
    # query never blocks the event loop (same convention as orchestrator.py).
    return await asyncio.to_thread(compute_backtest, None, limit)


@router.get("/{ticker}")
async def backtest_ticker(ticker: str, limit: int = Query(500, ge=1, le=5000)) -> dict:
    return await asyncio.to_thread(compute_backtest, ticker, limit)
