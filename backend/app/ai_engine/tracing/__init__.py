"""
Execution tracing — records a timed span per stage and persists the trace to
MongoDB. Gives per-execution observability: which stage ran, how long, provider,
tokens, errors, in order.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger

log = get_logger(__name__)


class Span(dict):
    """A single timed step in the execution trace."""


class ExecutionTracer:
    def __init__(self, analysis_id: str, ticker: str = "") -> None:
        self.analysis_id = analysis_id
        self.ticker = ticker
        self.spans: list[dict[str, Any]] = []
        self.started_at = datetime.now(timezone.utc).isoformat()

    @contextmanager
    def span(self, name: str, **attrs: Any):
        t0 = time.perf_counter()
        rec: dict[str, Any] = {
            "name": name, "start": datetime.now(timezone.utc).isoformat(),
            "attrs": attrs, "ok": True, "error": None,
        }
        try:
            yield rec
        except Exception as e:  # noqa: BLE001
            rec["ok"] = False
            rec["error"] = str(e)
            log.warning("trace span=%s FAILED: %s", name, e)
            raise
        finally:
            rec["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            self.spans.append(rec)
            log.info("trace span=%s latency=%.1fms ok=%s",
                     name, rec["latency_ms"], rec["ok"])

    def add(self, name: str, latency_ms: float = 0.0, **attrs: Any) -> None:
        self.spans.append({
            "name": name, "start": datetime.now(timezone.utc).isoformat(),
            "latency_ms": latency_ms, "attrs": attrs, "ok": True, "error": None,
        })

    def to_doc(self) -> dict[str, Any]:
        total = sum(s.get("latency_ms", 0) for s in self.spans)
        return {
            "analysis_id": self.analysis_id, "ticker": self.ticker,
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "total_latency_ms": round(total, 2),
            "span_count": len(self.spans), "spans": self.spans,
        }

    async def persist(self) -> None:
        """Best-effort write of the trace to Mongo."""
        try:
            from app.db import mongo as _m
            await _m.get_mongo()["execution_traces"].update_one(
                {"analysis_id": self.analysis_id},
                {"$set": self.to_doc()}, upsert=True,
            )
        except Exception as e:  # noqa: BLE001
            log.debug("trace persist skipped: %s", e)
