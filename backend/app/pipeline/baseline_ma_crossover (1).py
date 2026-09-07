"""
Moving Average Crossover -- a standard, well-known "naive baseline" trading
strategy, added for direct comparison against RAEM's multi-agent decisions
in Backtest & Accuracy.

Signal logic (the classic "golden cross" / "death cross"):
  - short-window SMA crosses ABOVE the long-window SMA (wasn't above
    yesterday)  -> BUY
  - short-window SMA crosses BELOW the long-window SMA (wasn't below
    yesterday)  -> SELL
  - no fresh crossover today                            -> HOLD

Deliberately "dumb" by design -- no fundamentals, no news, no debate, just
two moving averages on the same OHLCV data RAEM's own Market Analyst
already fetches. That's the point of a baseline: if RAEM can't beat this
on Sharpe/Win-Rate/Cumulative-Return, the added complexity (multi-agent
debate, episodic memory, post-mortem) isn't earning its keep for that
ticker/regime -- a standard sanity check in trading-strategy research.

Reuses RAEM's own DSE data tools (_fetch_ohlcv, stockstats-based indicator
computation -- same library Market Analyst uses) and RAEMMemory.save_episode()
so baseline decisions are stored as ordinary episodes, tagged with a
provider label that slots straight into the existing by_llm_provider
comparison in app/services/backtest.py -- no new comparison UI/backend
needed, "baseline:ma-crossover" just shows up as another column/curve next
to "kimi:kimi-k3" and "anthropic:claude-sonnet-5".
"""

from __future__ import annotations

from datetime import datetime, timedelta

SHORT_WINDOW = 10
LONG_WINDOW = 50
PROVIDER_LABEL = f"baseline:ma-crossover-{SHORT_WINDOW}-{LONG_WINDOW}"


def compute_ma_crossover_signal(company: str, as_of_date: str,
                                 short_window: int = SHORT_WINDOW,
                                 long_window: int = LONG_WINDOW) -> dict:
    """Fetches OHLCV up to `as_of_date`, computes today's and yesterday's
    short/long SMA, and returns the crossover-implied signal.

    Returns a dict with keys: signal (BUY/SELL/HOLD), entry_price,
    short_sma, long_sma, short_sma_prev, long_sma_prev, rsi, macd,
    boll_ub, boll_lb -- or {"signal": None, "error": "..."} if there isn't
    enough trailing history yet for the long window (common for newly
    listed or thinly-traded DSE tickers).
    """
    from tradingagents.dataflows.dse_stock_data import _fetch_ohlcv
    from stockstats import wrap

    end_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    # long_window trading days needs roughly long_window * 1.6 calendar
    # days (weekends/holidays) -- plus a bit of buffer, plus one extra day
    # so we can also compute *yesterday's* SMA pair to detect a fresh cross.
    start_dt = end_dt - timedelta(days=int(long_window * 1.6) + 15)

    df = _fetch_ohlcv(company, start_dt.strftime("%Y-%m-%d"), as_of_date)
    closes = df["Close"].tolist()
    if len(closes) < long_window + 1:
        return {"signal": None,
                "error": f"only {len(closes)} trading day(s) of history, need >= {long_window + 1}"}

    def sma(vals: list[float], window: int) -> float:
        return sum(vals[-window:]) / window

    short_now, long_now = sma(closes, short_window), sma(closes, long_window)
    short_prev, long_prev = sma(closes[:-1], short_window), sma(closes[:-1], long_window)

    was_above = short_prev > long_prev
    is_above = short_now > long_now
    if is_above and not was_above:
        signal = "BUY"
    elif not is_above and was_above:
        signal = "SELL"
    else:
        signal = "HOLD"

    # RSI/MACD/Bollinger via the same stockstats library Market Analyst
    # uses (see get_indicators in this same module) -- purely so baseline
    # episodes get a real regime tag via classify_regime(), making them
    # comparable in the by_regime backtest breakdown too, not just
    # by_llm_provider.
    stats = wrap(df.copy())
    rsi = float(stats["rsi"].iloc[-1]) if not stats.empty else None
    macd = float(stats["macd"].iloc[-1]) if not stats.empty else None
    boll_ub = float(stats["boll_ub"].iloc[-1]) if not stats.empty else None
    boll_lb = float(stats["boll_lb"].iloc[-1]) if not stats.empty else None

    return {
        "signal": signal, "entry_price": round(closes[-1], 2),
        "short_sma": round(short_now, 2), "long_sma": round(long_now, 2),
        "short_sma_prev": round(short_prev, 2), "long_sma_prev": round(long_prev, 2),
        "rsi": rsi, "macd": macd, "boll_ub": boll_ub, "boll_lb": boll_lb,
    }


def save_baseline_episode(memory, company: str, as_of_date: str,
                          short_window: int = SHORT_WINDOW,
                          long_window: int = LONG_WINDOW,
                          run_key: str | None = None) -> dict:
    """Computes today's MA-crossover signal and saves it as an ordinary
    RAEM episode via the same RAEMMemory.save_episode() the real pipeline
    uses -- so it's resolved by the same backfill_pending_outcomes(),
    shows up in the same Backtest page, and compares directly against
    Kimi/Sonnet episodes in by_llm_provider. `memory` is a RAEMMemory
    instance (see app/pipeline/memory.py)."""
    from tradingagents.agents.utils.agent_utils import get_stock_data

    result = compute_ma_crossover_signal(company, as_of_date, short_window, long_window)
    if result["signal"] is None:
        return {"saved": False, "reason": result["error"]}

    # Same CSV-formatted stock_data build_episode_document() already knows
    # how to pull an entry price from (its own reversed-scan-for-last-
    # valid-close logic) -- reusing the real tool output here instead of
    # hand-rolling a second CSV format avoids yet another parsing mismatch.
    start_dt = datetime.strptime(as_of_date, "%Y-%m-%d") - timedelta(days=45)
    stock_data = get_stock_data.invoke({
        "symbol": company, "start_date": start_dt.strftime("%Y-%m-%d"), "end_date": as_of_date,
    })

    decision_text = (
        f"Moving Average Crossover Baseline ({short_window}-day / {long_window}-day SMA)\n"
        f"Short SMA: {result['short_sma']} (prev: {result['short_sma_prev']})\n"
        f"Long SMA: {result['long_sma']} (prev: {result['long_sma_prev']})\n"
        f"No fundamentals, news, or debate -- pure price-crossover rule, "
        f"used as a naive baseline against the full RAEM pipeline.\n"
        f"FINAL TRANSACTION PROPOSAL: **{result['signal']}**"
    )
    indicators = {"rsi": result["rsi"], "macd": result["macd"],
                  "boll_ub": result["boll_ub"], "boll_lb": result["boll_lb"]}

    saved = memory.save_episode(
        company, as_of_date, indicators,
        fund_metrics={}, news_metrics={}, sentiment_metrics={},
        final_decision_text=decision_text, stock_data=stock_data,
        llm_provider=PROVIDER_LABEL,
        run_key=run_key or f"ma-crossover-{as_of_date}",
    )
    return {"saved": True, "signal": result["signal"], "entry_price": result["entry_price"],
            "episode": saved}
