"""
One-time migration: fix stale "outcome" metadata on already-RESOLVED episodes.

Background: RAEM episodes carry two parallel status fields --
  - "outcome_status" / "outcome_label"  (read by the RAEM pipeline itself:
     Post-Mortem stage, _memory_context(), reflect_on_regime_transition)
  - "outcome"                            (read by MemoryRecord.from_chroma,
     i.e. the Memory API / the "RAEM Memory" panel in the UI)

`backfill_pending_outcomes()` in app/pipeline/memory.py used to only update
the first set when resolving a PENDING episode, so the "outcome" key stayed
stuck on "PENDING" forever -- even for episodes that were fully resolved to
WIN/LOSS/FLAT. That write path is now fixed to update both keys going
forward; this script is a one-time sweep to repair episodes that were
already resolved *before* that fix landed.

Usage:
    cd backend
    python -m tools.sync_outcome_keys                # all tickers
    python -m tools.sync_outcome_keys --company BATBC # one ticker only

Safe to re-run -- episodes already in sync are skipped (no-op).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make `app` importable when run as a script from the backend/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.memory import RAEMMemory  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company", default=None,
                         help="Limit the sweep to one ticker (default: all).")
    args = parser.parse_args()

    mem = RAEMMemory()
    result = mem.sync_outcome_keys(company=args.company)

    print(f"Checked {result.get('checked', 0)} RESOLVED episode(s)"
          + (f" for {args.company}" if args.company else " across all tickers")
          + f", fixed {result.get('fixed', 0)}.")

    if result.get("note"):
        print(f"Note: {result['note']}")

    details = result.get("details", [])
    if details:
        print("\nFixed episodes:")
        for d in details:
            print(f"  - {d.get('company')} · {d.get('trade_date')} -> outcome={d.get('outcome_label')}")
    elif result.get("fixed", 0) == 0 and not result.get("note"):
        print("Nothing to fix -- all RESOLVED episodes already have a synced outcome key.")

    print("\nFull result:")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
