"""
Backtest / accuracy aggregation — rolls up RESOLVED RAEM episodes (real P&L
outcomes, backfilled once enough days have passed — see
pipeline/memory.py::backfill_pending_outcomes) into win-rate / P&L stats,
sliceable by signal, regime, macro regime, and verifier status.

Reuses RAEMMemory directly rather than the generic MemoryManager/Collection
path (app/ai_engine/memory) because RAEM's episode metadata schema
(trade_date, final_signal, outcome_status, pnl_pct, regime, macro_regime,
verifier_status, ...) is RAEM-specific and doesn't map onto the platform's
generic MemoryRecord schema used by the /memory/* routes for other
collections — going through that path would silently drop/garble most of
these fields.
"""

from __future__ import annotations

from app.pipeline.memory import RAEMMemory


def _safe_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _bucket(episodes: list[dict], key: str) -> dict[str, dict]:
    """Win-rate / avg-P&L breakdown keyed by a metadata field."""
    out: dict[str, dict] = {}
    for ep in episodes:
        m = ep["metadata"]
        k = m.get(key) or "N/A"
        b = out.setdefault(k, {"count": 0, "wins": 0, "losses": 0, "flats": 0, "pnl_sum": 0.0})
        b["count"] += 1
        b["pnl_sum"] += _safe_float(m.get("pnl_pct"))
        label = m.get("outcome_label")
        if label == "WIN":
            b["wins"] += 1
        elif label == "LOSS":
            b["losses"] += 1
        else:
            b["flats"] += 1
    for b in out.values():
        b["win_rate"] = round(b["wins"] / b["count"], 3) if b["count"] else 0.0
        b["avg_pnl_pct"] = round(b["pnl_sum"] / b["count"], 3) if b["count"] else 0.0
        del b["pnl_sum"]
    return out


def compute_backtest(ticker: str | None = None, limit: int = 500) -> dict:
    """Aggregates a ticker's (or all tickers', if ticker is None) RESOLVED
    episodes into overall + sliced win-rate/P&L stats plus a chronological
    cumulative-P&L curve for charting."""
    memory = RAEMMemory()
    all_eps = memory.list_episodes(company=ticker.upper() if ticker else None, limit=limit)
    resolved = [e for e in all_eps if e["metadata"].get("outcome_status") == "RESOLVED"]
    resolved.sort(key=lambda e: e["metadata"].get("trade_date", ""))  # chronological

    wins = sum(1 for e in resolved if e["metadata"].get("outcome_label") == "WIN")
    losses = sum(1 for e in resolved if e["metadata"].get("outcome_label") == "LOSS")
    flats = len(resolved) - wins - losses
    pnl_values = [_safe_float(e["metadata"].get("pnl_pct")) for e in resolved]
    avg_pnl = round(sum(pnl_values) / len(pnl_values), 3) if pnl_values else 0.0
    win_rate = round(wins / len(resolved), 3) if resolved else 0.0

    cumulative = 0.0
    curve = []
    for e in resolved:
        m = e["metadata"]
        pnl = _safe_float(m.get("pnl_pct"))
        cumulative += pnl
        curve.append({
            "trade_date": m.get("trade_date", ""),
            "ticker": m.get("company", ""),
            "signal": m.get("final_signal", ""),
            "regime": m.get("regime", ""),
            "macro_regime": m.get("macro_regime", "N/A"),
            "verifier_status": m.get("verifier_status", "N/A"),
            "pnl_pct": pnl,
            "cumulative_pnl_pct": round(cumulative, 3),
            "outcome_label": m.get("outcome_label", ""),
        })

    return {
        "ticker": ticker.upper() if ticker else None,
        "total_episodes": len(all_eps),
        "resolved_episodes": len(resolved),
        "pending_episodes": len(all_eps) - len(resolved),
        "wins": wins, "losses": losses, "flats": flats,
        "win_rate": win_rate, "avg_pnl_pct": avg_pnl,
        "by_signal": _bucket(resolved, "final_signal"),
        "by_regime": _bucket(resolved, "regime"),
        "by_macro_regime": _bucket(resolved, "macro_regime"),
        "by_verifier_status": _bucket(resolved, "verifier_status"),
        "curve": curve,
    }
