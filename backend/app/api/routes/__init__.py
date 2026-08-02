"""Aggregate all API routers."""

from fastapi import APIRouter

from app.api.routes import (
    analysis,
    backtest,
    dataset,
    health,
    memory,
    paper_trading,
    stocks,
    watchlist,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(stocks.router)
api_router.include_router(memory.router)
api_router.include_router(analysis.router)
api_router.include_router(watchlist.router)
api_router.include_router(dataset.router)
api_router.include_router(backtest.router)
api_router.include_router(paper_trading.router)

# Unversioned WebSocket router for per-analysis streaming (/ws/analysis/{id}).
analysis_ws_router = analysis.ws_router
