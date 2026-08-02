"""Watchlist API — server-side tracked-ticker list.

    GET    /watchlist            current tickers
    POST   /watchlist            add a ticker  {"ticker": "AAPL"}
    DELETE /watchlist/{ticker}   remove a ticker

This is the list the scheduled dataset-export job (app/workers/scheduler.py)
reads every run, so it must live server-side rather than only in the
browser's localStorage.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter

from app.models.watchlist import WatchlistResponse
from app.services.watchlist_store import WatchlistStore

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class AddTickerBody(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=12)


@router.get("", response_model=WatchlistResponse)
async def get_watchlist() -> WatchlistResponse:
    return WatchlistResponse(tickers=await WatchlistStore.list_tickers())


@router.post("", response_model=WatchlistResponse)
async def add_ticker(body: AddTickerBody) -> WatchlistResponse:
    return WatchlistResponse(tickers=await WatchlistStore.add(body.ticker))


@router.delete("/{ticker}", response_model=WatchlistResponse)
async def remove_ticker(ticker: str) -> WatchlistResponse:
    return WatchlistResponse(tickers=await WatchlistStore.remove(ticker))
