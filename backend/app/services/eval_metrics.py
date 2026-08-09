"""
Performance-evaluation metrics for RAEM's resolved trade history.

Implements the six metrics from the thesis evaluation methodology chapter:
  Cumulative/Final Return, Sharpe Ratio, Sortino Ratio, Maximum Drawdown,
  Win Rate, Calmar Ratio
over a chronological series of per-trade P&L outcomes (RESOLVED episodes'
pnl_pct, sourced from pipeline/memory.py::backfill_pending_outcomes).

IMPORTANT — what these numbers do and don't mean here:
  - Each RESOLVED episode's pnl_pct is treated as ONE return observation
    (a single trade's outcome), not a daily/periodic portfolio return.
    The Risk Facilitator's position-sizing text (e.g. "6% of portfolio")
    is advisory and is NOT applied here — these are unweighted, per-trade
    returns, as if every trade used the same capital. For capital-weighted
    portfolio metrics, scale each pnl_pct by its episode's position size
    before calling these functions.
  - Sharpe/Sortino are annualised using the OBSERVED trading frequency
    (trade_count / years spanned by the episode dates), since RAEM trades
    are event-driven (one signal per ticker per run), not on a fixed
    daily/weekly grid. Pass `periods_per_year` to override with a fixed
    convention (e.g. 252) instead.
  - Sharpe/Sortino/Calmar need at least 2 dated, resolved trades with
    non-zero spread to be statistically meaningful; return None rather
    than a fabricated number otherwise — same "don't invent stats from a
    tiny sample" principle the Post-Mortem agent prompt already enforces
    elsewhere in this codebase (see pipeline/agents.py::run_post_mortem).
"""

from __future__ import annotations

import math
from datetime import datetime


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _to_returns(pnl_series: list[float]) -> list[float]:
    """pnl_pct values (e.g. 4.2 meaning +4.2%) -> decimal returns (0.042)."""
    return [p / 100.0 for p in pnl_series]


def _years_spanned(trade_dates: list[str]) -> float:
    dates = sorted(d for d in trade_dates if d)
    if len(dates) < 2:
        return 0.0
    fmt = "%Y-%m-%d"
    try:
        span_days = (datetime.strptime(dates[-1], fmt) - datetime.strptime(dates[0], fmt)).days
    except ValueError:
        return 0.0
    return span_days / 365.25 if span_days > 0 else 0.0


def _infer_periods_per_year(trade_dates: list[str] | None, n_trades: int) -> float:
    """Trades-per-year implied by the actual dated history, falling back to
    252 (standard trading-day convention) if dates aren't available or
    span too little time to infer a rate."""
    if not trade_dates:
        return 252.0
    years = _years_spanned(trade_dates)
    if years <= 0:
        return 252.0
    return n_trades / years


# --------------------------------------------------------------------------
# The six metrics
# --------------------------------------------------------------------------
def cumulative_return_pct(pnl_series: list[float], compounding: bool = True) -> float:
    """Total capital growth over the period.

    compounding=True (default): (1+r1)*(1+r2)*...*(1+rn) - 1 — correct if
    each trade re-invests the prior trade's outcome (single capital pool,
    fully at risk each time).
    compounding=False: simple sum of pnl_pct — matches the additive
    "cumulative_pnl_pct" curve already used in app/services/backtest.py,
    useful if you want exact continuity with that chart's numbers.
    """
    if not pnl_series:
        return 0.0
    if not compounding:
        return round(sum(pnl_series), 3)
    equity = 1.0
    for r in _to_returns(pnl_series):
        equity *= (1 + r)
    return round((equity - 1) * 100, 3)


def sharpe_ratio(pnl_series: list[float], trade_dates: list[str] | None = None,
                  periods_per_year: float | None = None,
                  risk_free_rate: float = 0.0) -> float | None:
    """Return per unit of TOTAL volatility.
    Sharpe = (mean(r) - rf_per_trade) / std(r) * sqrt(periods_per_year)
    """
    returns = _to_returns(pnl_series)
    if len(returns) < 2:
        return None
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    std_r = math.sqrt(variance)
    if std_r == 0:
        return None
    ppy = periods_per_year or _infer_periods_per_year(trade_dates, len(returns))
    rf_per_trade = risk_free_rate / ppy if ppy else 0.0
    return round(((mean_r - rf_per_trade) / std_r) * math.sqrt(ppy), 3)


def sortino_ratio(pnl_series: list[float], trade_dates: list[str] | None = None,
                   periods_per_year: float | None = None,
                   risk_free_rate: float = 0.0) -> float | None:
    """Return per unit of DOWNSIDE volatility only (losing trades only)."""
    returns = _to_returns(pnl_series)
    if len(returns) < 2:
        return None
    mean_r = sum(returns) / len(returns)
    downside = [min(r, 0.0) for r in returns]
    downside_var = sum(d ** 2 for d in downside) / len(returns)
    downside_std = math.sqrt(downside_var)
    if downside_std == 0:
        return None  # no losing trades yet in this sample -- undefined, not infinite
    ppy = periods_per_year or _infer_periods_per_year(trade_dates, len(returns))
    rf_per_trade = risk_free_rate / ppy if ppy else 0.0
    return round(((mean_r - rf_per_trade) / downside_std) * math.sqrt(ppy), 3)


def max_drawdown_pct(pnl_series: list[float]) -> float:
    """Worst peak-to-trough decline on the compounded equity curve.
    Returned as a negative percentage (e.g. -12.4 meaning -12.4%), 0.0 if
    the curve never dips below a prior peak."""
    if not pnl_series:
        return 0.0
    equity, peak, max_dd = 1.0, 1.0, 0.0
    for r in _to_returns(pnl_series):
        equity *= (1 + r)
        peak = max(peak, equity)
        dd = (equity - peak) / peak
        max_dd = min(max_dd, dd)
    return round(max_dd * 100, 3)


def win_rate_pct(outcome_labels: list[str]) -> float:
    """Proportion of profitable (WIN-labelled) trades out of all resolved
    trades. FLAT and LOSS both count against it, matching outcome_label's
    existing 3-way WIN/LOSS/FLAT split used elsewhere (post-mortem,
    backtest.py)."""
    if not outcome_labels:
        return 0.0
    wins = sum(1 for lbl in outcome_labels if lbl == "WIN")
    return round(wins / len(outcome_labels) * 100, 3)


def calmar_ratio(pnl_series: list[float], trade_dates: list[str] | None = None) -> float | None:
    """Annualised return / max drawdown. Needs the actual calendar span
    (trade_dates) to annualise correctly; returns None with fewer than 2
    dated trades or a zero drawdown (nothing to divide by)."""
    if not trade_dates or len(trade_dates) < 2:
        return None
    dd = max_drawdown_pct(pnl_series)
    if dd == 0:
        return None
    years = _years_spanned(trade_dates)
    if years <= 0:
        return None
    total_return = cumulative_return_pct(pnl_series, compounding=True) / 100
    annualised_return = (1 + total_return) ** (1 / years) - 1
    return round((annualised_return * 100) / abs(dd), 3)


# --------------------------------------------------------------------------
# Convenience wrapper
# --------------------------------------------------------------------------
def compute_evaluation_metrics(episode_metadatas: list[dict]) -> dict:
    """Takes a list of RESOLVED episode metadata dicts (chronological order
    not required -- sorted internally by trade_date) and returns all six
    metrics in one dict, ready to merge into an API response or a thesis
    results table.

    `episode_metadatas` items are the raw Chroma metadata dicts (the ones
    with string-typed pnl_pct/trade_date/outcome_label, as stored by
    build_episode_document / backfill_pending_outcomes) -- pass
    `ep["metadata"]` from RAEMMemory.list_episodes()/get(), not the
    wrapper dict itself.
    """
    rows = sorted(episode_metadatas, key=lambda m: m.get("trade_date", ""))
    pnl_series = [_safe_float(m.get("pnl_pct")) for m in rows]
    trade_dates = [m.get("trade_date", "") for m in rows]
    outcome_labels = [m.get("outcome_label", "") for m in rows]

    return {
        "n_trades": len(rows),
        "cumulative_return_pct": cumulative_return_pct(pnl_series),
        "sharpe_ratio": sharpe_ratio(pnl_series, trade_dates),
        "sortino_ratio": sortino_ratio(pnl_series, trade_dates),
        "max_drawdown_pct": max_drawdown_pct(pnl_series),
        "win_rate_pct": win_rate_pct(outcome_labels),
        "calmar_ratio": calmar_ratio(pnl_series, trade_dates),
    }
