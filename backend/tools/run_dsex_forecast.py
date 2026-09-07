"""
Runs a real DSEX ARIMA forecast + chart, using live data (via bdshare,
same source as the Macro Regime Analyst's own snapshot). Run this ON YOUR
OWN BACKEND (Railway, or locally with the same environment) -- it needs
network access to dsebd.org, which a sandboxed dev environment may not
have.

Usage:
    cd backend
    python -m tools.run_dsex_forecast
    python -m tools.run_dsex_forecast --horizon 60 --lookback 500 --out dsex_forecast.png
    python -m tools.run_dsex_forecast --date 2026-08-12 --order 3,1,2
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date as _date

sys.path.insert(0, ".")

from app.pipeline.dsex_forecast import forecast_dsex, render_dsex_forecast_chart  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", default=None, help="As-of date YYYY-MM-DD (default: today)")
    parser.add_argument("--horizon", type=int, default=30, help="Days ahead to forecast (default: 30)")
    parser.add_argument("--lookback", type=int, default=365, help="Days of history to fit on (default: 365)")
    parser.add_argument("--order", default="2,1,2", help="ARIMA (p,d,q) order, comma-separated (default: 2,1,2)")
    parser.add_argument("--out", default="dsex_forecast.png", help="Output chart path (default: dsex_forecast.png)")
    parser.add_argument("--json-out", default=None, help="Optional: also dump the raw forecast data as JSON")
    args = parser.parse_args()

    as_of = args.date or _date.today().strftime("%Y-%m-%d")
    order = tuple(int(x) for x in args.order.split(","))

    print(f"Fetching DSEX history and fitting ARIMA{order} as of {as_of}...")
    result = forecast_dsex(as_of, horizon_days=args.horizon, lookback_days=args.lookback, order=order)

    print(f"History: {len(result['history'])} trading day(s), "
          f"last close {result['history'][-1]['close']} on {result['history'][-1]['date']}")
    print(f"Forecast (day 1): {result['forecast'][0]}")
    print(f"Forecast (day {args.horizon}): {result['forecast'][-1]}")

    render_dsex_forecast_chart(result, args.out)
    print(f"\nChart saved to: {args.out}")

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Raw forecast data saved to: {args.json_out}")


if __name__ == "__main__":
    main()
