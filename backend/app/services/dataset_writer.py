"""
Dataset writer — appends one row per completed analysis to a per-ticker CSV,
building a growing historical dataset of fetched data + agent decisions over
time. One file per ticker under settings.DATASET_CSV_PATH, e.g.
/data/dataset/AAPL.csv.

Called from two places: the scheduled dataset job (app/workers/scheduler.py)
after each automatic run, and optionally after any manual analysis too (see
app/ai_engine/orchestrator.py) so the dataset grows from every run, not just
scheduled ones.

Only ever appends (never rewrites), so the file is safe to open/tail while the
app is running.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone

from app.ai_engine.state import ExecutionState
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

FIELDNAMES = [
    "date", "created_at", "analysis_id", "ticker",
    "signal", "effective_signal", "confidence",
    "regime", "macro_regime", "verifier_status", "auto_overridden",
    "rsi", "macd", "pe_ratio", "eps_ttm", "news_sentiment",
    "entry_price", "stop_loss", "take_profit",
    "post_mortem_episodes_reviewed", "reasoning_snippet",
]


def _path_for(ticker: str) -> str:
    os.makedirs(settings.DATASET_CSV_PATH, exist_ok=True)
    return os.path.join(settings.DATASET_CSV_PATH, f"{ticker.upper()}.csv")


def _row_from_state(state: ExecutionState) -> dict:
    rec = state.recommendation
    tech = state.agents.get("TechnicalAnalyst")
    fund = state.agents.get("FundamentalAnalyst")
    news = state.agents.get("NewsAnalyst")
    indicators = (tech.metadata.get("indicators") if tech else {}) or {}
    fund_metrics = (fund.metadata.get("metrics") if fund else {}) or {}
    news_metrics = (news.metadata.get("news_metrics") if news else {}) or {}

    effective_signal = (
        state.verifier.effective_signal.value if state.verifier
        else (rec.signal.value if rec else "N/A")
    )

    return {
        "date": state.request.date or state.created_at[:10],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "analysis_id": state.analysis_id,
        "ticker": state.ticker,
        "signal": rec.signal.value if rec else "N/A",
        "effective_signal": effective_signal,
        "confidence": rec.confidence if rec else 0.0,
        "regime": state.memory.regime if state.memory else "",
        "macro_regime": state.macro.regime if state.macro else "",
        "verifier_status": state.verifier.status if state.verifier else "",
        "auto_overridden": state.verifier.auto_overridden if state.verifier else False,
        "rsi": indicators.get("rsi", ""),
        "macd": indicators.get("macd", ""),
        "pe_ratio": fund_metrics.get("pe_ratio", ""),
        "eps_ttm": fund_metrics.get("eps_ttm", ""),
        "news_sentiment": news_metrics.get("overall_sentiment", ""),
        "entry_price": rec.entry_price if rec else None,
        "stop_loss": rec.stop_loss if rec else None,
        "take_profit": rec.take_profit if rec else None,
        "post_mortem_episodes_reviewed": state.post_mortem.episodes_reviewed if state.post_mortem else 0,
        "reasoning_snippet": (rec.reasoning[:300].replace("\n", " ") if rec and rec.reasoning else ""),
    }


def append_row(state: ExecutionState) -> str:
    """Appends one row for this completed execution. Returns the file path."""
    path = _path_for(state.ticker)
    row = _row_from_state(state)
    is_new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if is_new:
            writer.writeheader()
        writer.writerow(row)
    log.info("dataset row appended ticker=%s file=%s", state.ticker, path)
    return path


def list_datasets() -> list[dict]:
    """One entry per ticker CSV that exists: ticker, row count, last modified."""
    if not os.path.isdir(settings.DATASET_CSV_PATH):
        return []
    out = []
    for fname in sorted(os.listdir(settings.DATASET_CSV_PATH)):
        if not fname.endswith(".csv"):
            continue
        path = os.path.join(settings.DATASET_CSV_PATH, fname)
        try:
            with open(path, encoding="utf-8") as f:
                row_count = max(0, sum(1 for _ in f) - 1)  # minus header
            out.append({
                "ticker": fname[:-4],
                "rows": row_count,
                "updated_at": datetime.fromtimestamp(
                    os.path.getmtime(path), tz=timezone.utc).isoformat(),
            })
        except OSError as e:  # noqa: BLE001
            log.warning("dataset stat failed for %s: %s", path, e)
    return out


def read_rows(ticker: str, limit: int = 500) -> list[dict]:
    """Most recent `limit` rows for one ticker, newest first."""
    path = _path_for(ticker)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows.reverse()
    return rows[:limit]
