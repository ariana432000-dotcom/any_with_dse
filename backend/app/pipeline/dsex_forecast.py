"""
ARIMA forecast for the DSEX broad-market index -- historical closes plus a
forward-looking projection with confidence intervals, rendered as a chart
in the same style as standard financial-data dashboards (e.g. Trading
Economics' "Bangladesh Stock Market (DSE Broad)" chart).

Why ARIMA (over Moving-Average or Monte Carlo) for THIS specific target:
DSEX is a broad, market-cap-weighted aggregate of ~199 companies (see
classify_dse_macro_regime's own docs) -- it's structurally smoother and
less idiosyncratic than any single stock's price (one company's bad
quarter doesn't move it much), which is exactly the setting where a
classical autoregressive model earns its keep: there's real, exploitable
autocorrelation in the index's own recent path, without the company-
specific noise that makes ARIMA a poor fit for individual small-caps.

Why NOT a fixed ARIMA order search library (pmdarima etc.): keeping this
to statsmodels alone avoids an extra, occasionally fragile dependency.
ARIMA(2,1,2) is used as a reasonable, well-established general-purpose
order for a differenced (non-stationary) daily financial series -- if you
want a rigorously *selected* order later (via AIC/BIC grid search or
auto_arima), that's a natural follow-up, not a blocker to using this now.

Reuses the exact same DSEX-fetching call already used for the Macro Regime
Analyst's own snapshot (see app/pipeline/agents.py::fetch_dse_macro_snapshot),
so this pulls from the same, already-verified data source -- no new
scraping logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def fetch_dsex_history(as_of_date: str, lookback_days: int = 365) -> list[dict]:
    """Daily DSEX closes for the trailing `lookback_days` calendar days,
    e.g. lookback_days=365 for the same 1-year window as a typical
    dashboard chart. Returns [{"date": "YYYY-MM-DD", "close": float}, ...]
    in chronological order. Raises if bdshare returns nothing usable --
    callers should treat that as "DSEX data temporarily unavailable"
    (dsebd.org downtime/network issue), same failure mode
    fetch_dse_macro_snapshot already handles by falling back to the
    global VIX/10Y/DXY snapshot.
    """
    from bdshare import get_market_info_more_data

    end_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=lookback_days)
    df = get_market_info_more_data(start_dt.strftime("%Y-%m-%d"), as_of_date, code="DSEX")
    if df is None or df.empty or "DSEX Index" not in df.columns:
        raise ValueError(f"no DSEX data returned for {start_dt.date()}..{end_dt.date()}")

    date_col = "date" if "date" in df.columns else df.columns[0]
    rows = [
        {"date": str(d)[:10], "close": float(v)}
        for d, v in zip(df[date_col], df["DSEX Index"])
        if v not in (None, "")
    ]
    rows.sort(key=lambda r: r["date"])
    return rows


def forecast_dsex(as_of_date: str, horizon_days: int = 30, lookback_days: int = 365,
                  order: tuple[int, int, int] = (2, 1, 2)) -> dict:
    """Fits ARIMA(order) on the trailing `lookback_days` of DSEX closes and
    forecasts `horizon_days` trading days ahead with a 95% confidence
    interval.

    Returns {"history": [...], "forecast": [...], "order": order} where
    each forecast point is {"day": 1..horizon_days, "mean": float,
    "lower": float, "upper": float}. `history` is the same shape as
    fetch_dsex_history()'s output. Raises the same way fetch_dsex_history
    does if data can't be fetched, or ValueError if there's too little
    history for the given `order` to fit meaningfully (needs at least
    ~5x the AR+MA order as a rough floor).
    """
    from statsmodels.tsa.arima.model import ARIMA

    history = fetch_dsex_history(as_of_date, lookback_days)
    closes = [r["close"] for r in history]
    min_needed = max(30, (order[0] + order[2]) * 5)
    if len(closes) < min_needed:
        raise ValueError(f"only {len(closes)} DSEX close(s), need >= {min_needed} to fit ARIMA{order}")

    model = ARIMA(closes, order=order)
    fitted = model.fit()
    result = fitted.get_forecast(steps=horizon_days)
    mean = result.predicted_mean
    ci = result.conf_int(alpha=0.05)  # 95% CI

    forecast = [
        {"day": i + 1, "mean": round(float(mean[i]), 2),
         "lower": round(float(ci[i][0]), 2), "upper": round(float(ci[i][1]), 2)}
        for i in range(horizon_days)
    ]
    return {"history": history, "forecast": forecast, "order": list(order),
            "as_of_date": as_of_date, "horizon_days": horizon_days}


def render_dsex_forecast_chart(result: dict, out_path: str) -> str:
    """Renders `result` (from forecast_dsex()) as a PNG: the trailing
    history as a solid line, the forecast mean as a dashed continuation,
    and the 95% confidence interval as a shaded band -- the standard way
    professional forecasts (e.g. central-bank projections) are shown, and
    directly comparable in style to a typical index-chart dashboard.
    Returns `out_path`."""
    import matplotlib
    matplotlib.use("Agg")  # headless -- no display server needed
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import datetime as _dt

    hist_dates = [_dt.strptime(r["date"], "%Y-%m-%d") for r in result["history"]]
    hist_closes = [r["close"] for r in result["history"]]

    last_date = hist_dates[-1]
    fc_dates = [last_date + timedelta(days=i + 1) for i in range(len(result["forecast"]))]
    fc_mean = [p["mean"] for p in result["forecast"]]
    fc_lower = [p["lower"] for p in result["forecast"]]
    fc_upper = [p["upper"] for p in result["forecast"]]

    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=150)
    ax.plot(hist_dates, hist_closes, color="#1a56db", linewidth=1.4, label="DSEX (actual)")
    # bridge the gap so the dashed forecast visually connects to the last actual point
    bridge_dates = [last_date] + fc_dates
    bridge_mean = [hist_closes[-1]] + fc_mean
    ax.plot(bridge_dates, bridge_mean, color="#d97706", linewidth=1.6,
            linestyle="--", label=f"ARIMA{tuple(result['order'])} forecast")
    ax.fill_between([last_date] + fc_dates, [hist_closes[-1]] + fc_lower,
                    [hist_closes[-1]] + fc_upper, color="#d97706", alpha=0.15,
                    label="95% confidence interval")

    ax.set_title(f"DSEX Broad Index — {result['horizon_days']}-Day ARIMA Forecast "
                f"(as of {result['as_of_date']})", fontsize=13, fontweight="bold")
    ax.set_ylabel("Index level")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return out_path
