"""Watchlist response contract — server-side so the scheduled dataset job
(app/workers/scheduler.py) has a single source of truth for which tickers to
track, shared with the dashboard's Watchlist page."""

from __future__ import annotations

from pydantic import BaseModel


class WatchlistResponse(BaseModel):
    tickers: list[str]
