"""
Paper trading — a simulated portfolio the AI's recommendations can be tried
against without risking real money. Single local user, so there is exactly
one portfolio (Mongo doc _id="default"); reset any time to start over.

Fills use the same live keyless quote (app/services/market_data.py) the rest
of the platform uses, so simulated fills track real prices.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.logging import get_logger
from app.db import mongo as _mongo
from app.services import market_data as mds

log = get_logger(__name__)

_PORTFOLIO_ID = "default"
_DEFAULT_STARTING_CASH = 100_000.0


def _db():
    return _mongo.get_mongo()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fresh_portfolio(cash: float) -> dict:
    return {
        "_id": _PORTFOLIO_ID,
        "cash": cash,
        "starting_cash": cash,
        "positions": {},  # ticker -> {"shares": float, "avg_cost": float}
        "realized_pnl": 0.0,
        "created_at": _now(),
        "updated_at": _now(),
    }


async def _get_or_init_portfolio() -> dict:
    doc = await _db()["paper_portfolio"].find_one({"_id": _PORTFOLIO_ID})
    if doc:
        return doc
    doc = _fresh_portfolio(_DEFAULT_STARTING_CASH)
    await _db()["paper_portfolio"].insert_one(doc)
    return doc


async def reset_portfolio(starting_cash: float | None = None) -> dict:
    cash = starting_cash if starting_cash and starting_cash > 0 else _DEFAULT_STARTING_CASH
    doc = _fresh_portfolio(cash)
    await _db()["paper_portfolio"].replace_one({"_id": _PORTFOLIO_ID}, doc, upsert=True)
    await _db()["paper_trades"].delete_many({})
    return _view(doc)


async def execute_trade(ticker: str, side: str, shares: float) -> dict:
    """Executes a simulated BUY/SELL at the current quote price. Raises
    ValueError on any invalid request (bad side, non-positive shares, no
    price available, insufficient cash/shares) — the route maps that to a
    400 rather than a 500."""
    ticker = ticker.strip().upper()
    side = side.strip().upper()
    if side not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL")
    if shares <= 0:
        raise ValueError("shares must be positive")

    quote = await mds.get_quote(ticker)
    price = quote.get("price")
    if price is None:
        raise ValueError(f"no current price available for {ticker}")

    portfolio = await _get_or_init_portfolio()
    positions: dict = portfolio.get("positions", {})
    pos = positions.get(ticker, {"shares": 0.0, "avg_cost": 0.0})
    trade_value = shares * price
    realized_pnl_delta = 0.0

    if side == "BUY":
        if trade_value > portfolio["cash"] + 1e-6:
            raise ValueError(
                f"insufficient cash: need ${trade_value:,.2f}, have ${portfolio['cash']:,.2f}"
            )
        new_shares = pos["shares"] + shares
        new_avg_cost = (
            (pos["shares"] * pos["avg_cost"] + trade_value) / new_shares
            if new_shares > 0 else 0.0
        )
        positions[ticker] = {"shares": new_shares, "avg_cost": round(new_avg_cost, 4)}
        portfolio["cash"] -= trade_value
    else:  # SELL
        if shares > pos["shares"] + 1e-6:
            raise ValueError(
                f"insufficient shares: trying to sell {shares}, holding {pos['shares']}"
            )
        realized_pnl_delta = (price - pos["avg_cost"]) * shares
        remaining = pos["shares"] - shares
        if remaining <= 1e-9:
            positions.pop(ticker, None)
        else:
            positions[ticker] = {"shares": remaining, "avg_cost": pos["avg_cost"]}
        portfolio["cash"] += trade_value
        portfolio["realized_pnl"] = portfolio.get("realized_pnl", 0.0) + realized_pnl_delta

    portfolio["positions"] = positions
    portfolio["updated_at"] = _now()
    await _db()["paper_portfolio"].replace_one({"_id": _PORTFOLIO_ID}, portfolio, upsert=True)

    trade = {
        "ticker": ticker, "side": side, "shares": shares, "price": price,
        "value": round(trade_value, 2), "realized_pnl": round(realized_pnl_delta, 2),
        "cash_after": round(portfolio["cash"], 2), "created_at": _now(),
    }
    await _db()["paper_trades"].insert_one(dict(trade))
    # Return the same fully mark-to-market shape as get_valuation() (not the
    # raw internal doc) so the API is self-consistent — the frontend never
    # needs a second shape just for "portfolio right after a trade".
    return {"portfolio": await get_valuation(), "trade": trade}


async def get_trades(limit: int = 50) -> list[dict]:
    cur = _db()["paper_trades"].find().sort("created_at", -1).limit(limit)
    docs = await cur.to_list(length=limit)
    return [_mongo.serialize(d) for d in docs]


def _view(portfolio: dict) -> dict:
    out = dict(portfolio)
    out.pop("_id", None)
    return out


async def get_valuation() -> dict:
    """Cash + mark-to-market value of every open position, using live quotes."""
    portfolio = await _get_or_init_portfolio()
    positions: dict = portfolio.get("positions", {})
    position_views = []
    market_value_total = 0.0
    unrealized_total = 0.0

    for ticker, pos in positions.items():
        quote = await mds.get_quote(ticker)
        price = quote.get("price") or 0.0
        market_value = pos["shares"] * price
        unrealized = (price - pos["avg_cost"]) * pos["shares"]
        market_value_total += market_value
        unrealized_total += unrealized
        position_views.append({
            "ticker": ticker, "shares": pos["shares"], "avg_cost": pos["avg_cost"],
            "current_price": price, "market_value": round(market_value, 2),
            "unrealized_pnl": round(unrealized, 2),
            "unrealized_pnl_pct": round(
                ((price - pos["avg_cost"]) / pos["avg_cost"] * 100) if pos["avg_cost"] else 0.0, 2
            ),
        })

    cash = portfolio["cash"]
    equity = cash + market_value_total
    starting_cash = portfolio.get("starting_cash", _DEFAULT_STARTING_CASH)
    total_return_pct = ((equity - starting_cash) / starting_cash * 100) if starting_cash else 0.0

    return {
        "cash": round(cash, 2),
        "starting_cash": starting_cash,
        "realized_pnl": round(portfolio.get("realized_pnl", 0.0), 2),
        "unrealized_pnl": round(unrealized_total, 2),
        "market_value": round(market_value_total, 2),
        "equity": round(equity, 2),
        "total_return_pct": round(total_return_pct, 2),
        "positions": sorted(position_views, key=lambda p: p["market_value"], reverse=True),
        "updated_at": portfolio.get("updated_at"),
    }
