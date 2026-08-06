"""
Analysis store — MongoDB persistence for full executions and their status.

Stores the complete ExecutionState (market data, agent outputs, reasoning,
confidence, provider, tokens, latency, memory hits, timeline, recommendation,
metadata) so it can be fetched by id, listed per-ticker, and polled for status
by background clients.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.ai_engine.state import ExecutionState, ExecutionStatus
from app.core.logging import get_logger
from app.db import mongo as _mongo

log = get_logger(__name__)

_COLL = "analyses"


def _db():
    return _mongo.get_mongo()


def _serialize(doc):
    return _mongo.serialize(doc)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnalysisStore:
    @staticmethod
    async def save(state: ExecutionState) -> str:
        doc = state.model_dump(mode="json")
        doc["_id"] = state.analysis_id
        doc["updated_at"] = _now()
        try:
            await _db()[_COLL].replace_one(
                {"_id": state.analysis_id}, doc, upsert=True
            )
            log.info("analysis persisted id=%s status=%s", state.analysis_id, state.status)
        except Exception as e:  # noqa: BLE001
            log.warning("analysis persist failed id=%s: %s", state.analysis_id, e)
        return state.analysis_id

    @staticmethod
    async def set_status(analysis_id: str, status: ExecutionStatus,
                        task_id: str | None = None, error: str | None = None,
                        ticker: str | None = None) -> None:
        updates: dict[str, Any] = {"status": status.value, "updated_at": _now()}
        if task_id is not None:
            updates["task_id"] = task_id
        if error is not None:
            updates["error"] = error
        if ticker is not None:
            updates["ticker"] = ticker
        try:
            await _db()[_COLL].update_one(
                {"_id": analysis_id}, {"$set": updates}, upsert=True
            )
        except Exception as e:  # noqa: BLE001
            log.debug("set_status skipped id=%s: %s", analysis_id, e)

    @staticmethod
    async def get(analysis_id: str) -> dict[str, Any] | None:
        try:
            doc = await _db()[_COLL].find_one({"_id": analysis_id})
            return _serialize(doc)
        except Exception as e:  # noqa: BLE001
            log.debug("analysis get failed id=%s: %s", analysis_id, e)
            return None

    @staticmethod
    async def get_trace(analysis_id: str) -> dict[str, Any] | None:
        try:
            doc = await _db()["execution_traces"].find_one(
                {"analysis_id": analysis_id}
            )
            return _serialize(doc)
        except Exception as e:  # noqa: BLE001
            log.debug("trace get failed id=%s: %s", analysis_id, e)
            return None

    @staticmethod
    async def list_for_ticker(ticker: str, limit: int = 20) -> list[dict[str, Any]]:
        try:
            cur = _db()[_COLL].find(
                {"request.ticker": ticker.upper()}
            ).sort("created_at", -1).limit(limit)
            return [_serialize(d) for d in await cur.to_list(length=limit)]
        except Exception as e:  # noqa: BLE001
            log.debug("analysis list failed: %s", e)
            return []
