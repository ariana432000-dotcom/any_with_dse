"""
Backfills Moving Average Crossover baseline episodes for one or more DSE
tickers, across a date range -- so the "By LLM Provider" comparison in
Backtest & Accuracy has a naive baseline (see
app/pipeline/baseline_ma_crossover.py) alongside Kimi/Sonnet's real
RAEM decisions.

Usage:
    cd backend
    python -m tools.run_ma_crossover_baseline --tickers BATBC,ISLAMIBANK --start 2026-06-01 --end 2026-08-12
    python -m tools.run_ma_crossover_baseline --tickers BATBC --start 2026-06-01 --end 2026-08-12 --short 10 --long 50

One episode is saved per trading day the ticker actually has a close price
for (weekends/holidays are naturally skipped -- compute_ma_crossover_signal
just won't find enough/matching rows and that date is skipped, logged, and
the run continues). Each run uses a fresh --start/--end pair for the ticker
it's given; only days with >= (long window + 1) trading days of prior
history produce a signal, so the first `long` or so calendar days of any
ticker's history are silently skipped (correctly -- there's no valid crossover
before then).

Run this once to build up baseline history, then let backfill_pending_outcomes
(part of the normal Outcome Backfill stage, triggered whenever *any* new
RAEM analysis runs for that ticker) resolve each PENDING baseline episode
after >=1 day has passed, exactly like real RAEM episodes.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta

sys.path.insert(0, ".")

from app.pipeline.memory import RAEMMemory  # noqa: E402
from app.pipeline.baseline_ma_crossover import save_baseline_episode, SHORT_WINDOW, LONG_WINDOW  # noqa: E402


def daterange(start: str, end: str):
    d = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    while d <= end_dt:
        yield d.strftime("%Y-%m-%d")
        d += timedelta(days=1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tickers", required=True, help="Comma-separated DSE tickers, e.g. BATBC,ISLAMIBANK")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD (inclusive)")
    parser.add_argument("--short", type=int, default=SHORT_WINDOW, help=f"Short SMA window (default {SHORT_WINDOW})")
    parser.add_argument("--long", type=int, default=LONG_WINDOW, help=f"Long SMA window (default {LONG_WINDOW})")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    memory = RAEMMemory()

    saved_count, skipped_count = 0, 0
    for ticker in tickers:
        print(f"\n{ticker}:")
        for date in daterange(args.start, args.end):
            try:
                result = save_baseline_episode(memory, ticker, date, args.short, args.long,
                                                run_key=f"ma-crossover-{ticker}-{date}")
            except Exception as e:  # noqa: BLE001
                print(f"  {date}: FAILED ({e})")
                skipped_count += 1
                continue
            if result["saved"]:
                print(f"  {date}: {result['signal']} @ {result['entry_price']}")
                saved_count += 1
            else:
                print(f"  {date}: skipped ({result['reason']})")
                skipped_count += 1

    print(f"\nDone. {saved_count} baseline episode(s) saved, {skipped_count} day(s) skipped.")
    print("Check GET /backtest for this ticker -- \"baseline:ma-crossover-"
          f"{args.short}-{args.long}\" will appear in by_llm_provider once "
          "resolved (needs >=1 day to pass, same as any RAEM episode).")


if __name__ == "__main__":
    main()
