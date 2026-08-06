"""
Celery application for background analysis execution.

Broker + result backend default to the platform Redis. If Celery isn't installed
or no worker is running, the ExecutionService falls back to an in-process task,
so the platform still functions in single-process/dev mode.
"""

from __future__ import annotations

import os

from app.core.config import settings

try:
    from celery import Celery

    celery_app = Celery(
        "ainvest",
        broker=settings.REDIS_URL,
        backend=settings.REDIS_URL,
    )
    # Local CPU-only LLM inference (Ollama, no GPU) can easily take well over
    # 30 min across the ~13-stage / 20+ sequential-call pipeline. Defaults
    # raised accordingly; override via env if your model/hardware differs.
    _hard = int(os.environ.get("CELERY_TASK_TIME_LIMIT", "5400"))    # 90 min hard cap
    _soft = int(os.environ.get("CELERY_TASK_SOFT_TIME_LIMIT", "5100"))  # 85 min soft
    celery_app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_track_started=True,
        task_time_limit=_hard,
        task_soft_time_limit=_soft,
        worker_prefetch_multiplier=1,
        task_default_queue="analysis",
    )
    # Ensure tasks are registered when the worker imports this module.
    celery_app.autodiscover_tasks(["app.workers"])
except Exception:  # noqa: BLE001 — celery optional
    celery_app = None  # type: ignore
