"""
Execution service — the single entry point routes use to run an analysis.

Wires an EventEmitter to the WebSocket bus (Redis pub/sub) so progress streams
live, then delegates to the Orchestrator. Supports synchronous execution and
background dispatch (Celery if configured, else an asyncio background task).
"""

from __future__ import annotations

import asyncio

from app.ai_engine.events import EventEmitter, EventType
from app.ai_engine.orchestrator import Orchestrator, get_orchestrator
from app.ai_engine.state import ExecutionRequest, ExecutionState, ExecutionStatus
from app.core.logging import get_logger
from app.services.analysis_store import AnalysisStore
from app.core.config import settings #Ari

log = get_logger(__name__)


def _ws_sink():
    """An event sink that publishes to the WebSocket Redis channel."""
    from app.api.ws import publish_event

    async def sink(evt) -> None:
        await publish_event(evt.ws_payload())

    return sink


class ExecutionService:
    def __init__(self, orchestrator: Orchestrator | None = None) -> None:
        self.orch = orchestrator or get_orchestrator()

    def make_emitter(self, analysis_id: str, ticker: str) -> EventEmitter:
        em = EventEmitter(analysis_id, ticker)
        em.add_sink(_ws_sink())
        return em

    async def run_sync(self, request: ExecutionRequest) -> ExecutionState:
        """Run to completion, streaming events over WebSocket."""
        state = ExecutionState(request=request)
        emitter = self.make_emitter(state.analysis_id, request.ticker.upper())
        # reuse the pre-created id so the caller can correlate
        result = await self.orch.execute(request, emitter=self._rebind(emitter, state))
        return result

    @staticmethod
    def _rebind(emitter: EventEmitter, state: ExecutionState) -> EventEmitter:
        emitter.analysis_id = state.analysis_id
        return emitter

    async def dispatch_background(self, request: ExecutionRequest) -> dict:
        """
        Kick off a background execution. Returns {analysis_id, task_id, status}.
        Uses Celery if a broker is configured; otherwise an in-process task
        (so the platform still works without a Celery worker running).
        """
        state = ExecutionState(request=request, status=ExecutionStatus.PENDING)
        await AnalysisStore.set_status(state.analysis_id, ExecutionStatus.PENDING,
                                        ticker=request.ticker.upper())

        #Ari
        task_id = None
        if settings.CELERY_ENABLED:
            try:
                from app.workers.celery_app import celery_app  # noqa: F401
                from app.workers.tasks import run_analysis_task

                async_result = run_analysis_task.delay(
                    request.model_dump(), state.analysis_id
                )
                task_id = async_result.id
                log.info("dispatched celery task=%s analysis=%s", task_id, state.analysis_id)
            except Exception as e:  # noqa: BLE001
                log.info("celery unavailable (%s); running in-process background task", e)

        if task_id is None:
            asyncio.create_task(self._run_in_process(request, state.analysis_id))
            task_id = f"inproc:{state.analysis_id}"

        await AnalysisStore.set_status(state.analysis_id, ExecutionStatus.PENDING, task_id=task_id)
        return {"analysis_id": state.analysis_id, "task_id": task_id,
                "status": ExecutionStatus.PENDING.value}

    async def _run_in_process(self, request: ExecutionRequest, analysis_id: str) -> None:
        emitter = self.make_emitter(analysis_id, request.ticker.upper())
        state = ExecutionState(request=request)
        state.analysis_id = analysis_id
        emitter.analysis_id = analysis_id
        try:
            await self.orch.execute(request, emitter=emitter)
        except Exception as e:  # noqa: BLE001
            log.exception("background execution failed: %s", e)
            await AnalysisStore.set_status(analysis_id, ExecutionStatus.FAILED, error=str(e))


_service: ExecutionService | None = None


def get_execution_service() -> ExecutionService:
    global _service
    if _service is None:
        _service = ExecutionService()
    return _service
