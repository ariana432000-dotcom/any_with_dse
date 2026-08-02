"""
Celery task: run a full analysis in a worker process.

The Orchestrator is async; Celery tasks are sync, so we drive it with
asyncio.run inside the task. Events still stream because the emitter publishes to
Redis (shared with the API's WebSocket subscriber).
"""

from __future__ import annotations

import asyncio

from app.core.logging import get_logger

log = get_logger(__name__)

try:
    from app.workers.celery_app import celery_app
except Exception:  # noqa: BLE001
    celery_app = None


def _run(request_dict: dict, analysis_id: str) -> dict:
    from app.ai_engine.execution import get_execution_service
    from app.ai_engine.state import ExecutionRequest

    request = ExecutionRequest.model_validate(request_dict)
    service = get_execution_service()

    async def _go():
        emitter = service.make_emitter(analysis_id, request.ticker.upper())
        emitter.analysis_id = analysis_id
        state = await service.orch.execute(request, emitter=emitter)
        return {"analysis_id": state.analysis_id, "status": state.status.value,
                "signal": state.recommendation.signal.value if state.recommendation else "N/A"}

    return asyncio.run(_go())


if celery_app is not None:
    @celery_app.task(name="app.workers.tasks.run_analysis_task", bind=True)
    def run_analysis_task(self, request_dict: dict, analysis_id: str) -> dict:  # noqa: ANN001
        log.info("celery run_analysis_task start analysis=%s", analysis_id)
        try:
            return _run(request_dict, analysis_id)
        except Exception as e:  # noqa: BLE001 — includes SoftTimeLimitExceeded
            # Without this, a task that times out (or dies for any other
            # reason) leaves the Mongo record stuck at RUNNING forever, and
            # the frontend polls indefinitely with no error ever shown.
            log.exception("celery run_analysis_task failed analysis=%s: %s", analysis_id, e)
            try:
                from app.ai_engine.state import ExecutionStatus
                from app.services.analysis_store import AnalysisStore

                asyncio.run(AnalysisStore.set_status(
                    analysis_id, ExecutionStatus.FAILED,
                    error=f"{type(e).__name__}: {e}"[:500],
                ))
            except Exception:  # noqa: BLE001
                log.exception("failed to record task failure for analysis=%s", analysis_id)
            raise
else:  # pragma: no cover
    def run_analysis_task(request_dict: dict, analysis_id: str):  # type: ignore
        raise RuntimeError("Celery not available")
