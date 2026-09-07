"""
Per-stock ARIMA forecast -- the same statistical approach as
dsex_forecast.py, adapted for individual DSE tickers rather than the
broad DSEX index.

Individual stocks are noisier than the broad index (a single company's
news/results move its own price far more than they move the whole
market -- see dsex_forecast.py's own docstring for why ARIMA suits DSEX
well), so this deliberately uses a SIMPLER model order than the DSEX
forecast (ARIMA(1,1,0) by default -- a single autoregressive term after
differencing, close to a random walk with a mild trend term) rather than
ARIMA(2,1,2). A more complex order on a noisier, shorter series tends to
overfit and produce unstable, overconfident forecasts -- appropriate
caution for thinly-traded DSE small-caps in particular.

This is the statistical, code-computed forecast layer. The LLM-facing
"Forecast Analyst" prompt (see agents.py::create_forecast_analyst) is
instructed to report these numbers as-is, not to invent or adjust them --
same "don't let the LLM re-derive what code already computed correctly"
principle behind the Fundamentals Analyst's Current Price fix.
"""

from __future__ import annotations

from datetime import datetime, timedelta

DEFAULT_ORDER = (1, 1, 0)


def forecast_stock_price(company: str, as_of_date: str, horizon_days: int = 30,
                         lookback_days: int = 180,
                         order: tuple[int, int, int] = DEFAULT_ORDER) -> dict:
    """Fits ARIMA(order) on `company`'s trailing `lookback_days` of closes
    and forecasts `horizon_days` trading days ahead with a 95% CI.

    Returns {"entry_price": float, "forecast_price": float (the horizon-
    day-ahead point forecast), "forecast_lower": float, "forecast_upper":
    float, "horizon_days": int, "order": list, "n_history_days": int} on
    success, or {"forecast_price": None, "error": "..."} if there's too
    little history to fit meaningfully -- common for newly listed or
    very thinly-traded tickers, and callers (the Forecast Analyst node)
    should report this as "forecast unavailable" rather than a number,
    same pattern as every other "not enough data" case elsewhere in this
    codebase.
    """
    from tradingagents.dataflows.dse_stock_data import _fetch_ohlcv
    from statsmodels.tsa.arima.model import ARIMA

    end_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=lookback_days)
    df = _fetch_ohlcv(company, start_dt.strftime("%Y-%m-%d"), as_of_date)
    closes = df["Close"].dropna().tolist()

    min_needed = max(30, (order[0] + order[2]) * 8)
    if len(closes) < min_needed:
        return {"forecast_price": None,
                "error": f"only {len(closes)} trading day(s) of history, need >= {min_needed}"}

    try:
        model = ARIMA(closes, order=order)
        fitted = model.fit()
        result = fitted.get_forecast(steps=horizon_days)
    except Exception as e:  # noqa: BLE001 -- ARIMA can fail to converge on pathological series
        return {"forecast_price": None, "error": f"ARIMA fit failed: {e}"}

    mean = result.predicted_mean
    ci = result.conf_int(alpha=0.05)
    last_idx = horizon_days - 1

    return {
        "entry_price": round(closes[-1], 2),
        "forecast_price": round(float(mean[last_idx]), 2),
        "forecast_lower": round(float(ci[last_idx][0]), 2),
        "forecast_upper": round(float(ci[last_idx][1]), 2),
        "horizon_days": horizon_days,
        "order": list(order),
        "n_history_days": len(closes),
    }
