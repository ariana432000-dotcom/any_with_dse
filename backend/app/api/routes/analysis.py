"""
Analysis API — every request goes through the Orchestrator (no business logic
here, no direct TradingAgents/RAEM calls).

    POST /analysis                    run (sync) or dispatch (background)
    GET  /analysis/{id}               full structured AnalysisResponse
    GET  /analysis/{id}/trace         execution trace (spans/timings)
    GET  /analysis/{id}/agents        per-agent outputs
    GET  /analysis/ticker/{t}/history recent analyses for a ticker
    WS   /ws/analysis/{id}            live event stream for one execution
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.ai_engine.execution import get_execution_service
from app.ai_engine.state import ExecutionMetadata, ExecutionRequest
from app.core.logging import get_logger
from app.models.analysis import AnalysisResponse
from app.services.analysis_store import AnalysisStore

log = get_logger(__name__)
router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("")
async def create_analysis(
    request: ExecutionRequest,
) -> dict:
    """Run an analysis. If request.background is true, dispatch and return ids."""
    service = get_execution_service()
    if request.background:
        return await service.dispatch_background(request)
    state = await service.run_sync(request)
    return AnalysisResponse.from_state(state).model_dump()


@router.get("/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(
    analysis_id: str,
) -> AnalysisResponse:
    doc = await AnalysisStore.get(analysis_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")
    try:
        return AnalysisResponse.from_doc(doc)
    except ValidationError as e:
        # Early PENDING/RUNNING placeholder — dispatch_background() writes a
        # partial doc (status only) before the pipeline has produced a full
        # ExecutionState, so it can't be validated as one yet. Return a
        # minimal, valid response instead of a 500 so the frontend keeps
        # polling normally until the full record lands.
        #
        # NOTE: this also fires (silently, until now) if a *completed* doc
        # fails to validate for some other reason — e.g. a shape mismatch
        # introduced by a pipeline change. In that case the frontend gets
        # stuck showing PENDING/no recommendation forever even though the
        # doc's actual status is COMPLETED. Logging here so that case is
        # distinguishable from a genuine early placeholder in the logs.
        log.warning(
            "AnalysisResponse.from_doc validation failed id=%s status=%s: %s",
            analysis_id, doc.get("status"), e,
        )
        return AnalysisResponse(
            analysis_id=analysis_id,
            ticker=(doc.get("ticker") or doc.get("request", {}).get("ticker", "")).upper(),
            status=doc.get("status", "PENDING"),
            created_at=doc.get("created_at") or doc.get("updated_at") or "",
            metadata=ExecutionMetadata(),
        )


@router.get("/{analysis_id}/trace")
async def get_trace(
    analysis_id: str,
) -> dict:
    trace = await AnalysisStore.get_trace(analysis_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace


@router.get("/{analysis_id}/agents")
async def get_agents(
    analysis_id: str,
) -> dict:
    doc = await AnalysisStore.get(analysis_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {"analysis_id": analysis_id, "agents": doc.get("agents", {})}


@router.get("/ticker/{ticker}/history")
async def ticker_history(
    ticker: str,
    limit: int = 20,
) -> dict:
    return {"ticker": ticker.upper(),
            "analyses": await AnalysisStore.list_for_ticker(ticker, limit)}


# --------------------------------------------------------------------------
# Per-analysis WebSocket: subscribes to the shared Redis channel and forwards
# only the events for this analysis_id.
# --------------------------------------------------------------------------
ws_router = APIRouter()


@ws_router.websocket("/ws/analysis/{analysis_id}")
async def analysis_ws(ws: WebSocket, analysis_id: str) -> None:
    from app.api.ws import CHANNEL
    from app.db.redis_client import get_redis

    await ws.accept()
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(CHANNEL)
    await ws.send_json({"type": "SUBSCRIBED", "analysis_id": analysis_id})
    try:
        existing = await AnalysisStore.get(analysis_id)
        if existing:
            await ws.send_json({"type": "SNAPSHOT", "analysis_id": analysis_id,
                                "status": existing.get("status")})
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            try:
                payload = json.loads(msg["data"])
            except Exception:  # noqa: BLE001
                continue
            if payload.get("channel") == "analysis" and payload.get("analysis_id") == analysis_id:
                await ws.send_json(payload)
                if payload.get("type") in ("COMPLETED", "ERROR"):
                    await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        log.debug("analysis_ws error: %s", e)
    finally:
        try:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()
        except Exception:  # noqa: BLE001
            pass
