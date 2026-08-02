"""Paper trading API — a simulated portfolio, no real money involved.

    GET  /paper-trading/portfolio    current valuation (cash, positions, P&L)
    POST /paper-trading/trade        execute a simulated BUY/SELL
    GET  /paper-trading/trades       trade log, newest first
    POST /paper-trading/reset        wipe and restart with fresh cash
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services import paper_trading as pt

router = APIRouter(prefix="/paper-trading", tags=["paper-trading"])


class TradeRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=12)
    side: str  # BUY | SELL
    shares: float = Field(..., gt=0)


class ResetRequest(BaseModel):
    starting_cash: float | None = None


@router.get("/portfolio")
async def get_portfolio() -> dict:
    return await pt.get_valuation()


@router.post("/trade")
async def trade(body: TradeRequest) -> dict:
    try:
        return await pt.execute_trade(body.ticker, body.side, body.shares)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/trades")
async def trades(limit: int = Query(50, ge=1, le=500)) -> dict:
    return {"trades": await pt.get_trades(limit)}


@router.post("/reset")
async def reset(body: ResetRequest) -> dict:
    return await pt.reset_portfolio(body.starting_cash)
