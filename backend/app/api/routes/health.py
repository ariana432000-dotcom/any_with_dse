"""Health + readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.db.mongo import ping_mongo
from app.db.redis_client import ping_redis
from app.models.schemas import Health
from app.pipeline.llm import llm_info

router = APIRouter(tags=["health"])


def _ping_chroma() -> dict:
    """Chroma health via the MemoryManager (never touches Chroma directly)."""
    try:
        from app.ai_engine.memory import get_memory_manager
        h = get_memory_manager().health_check()
        return {"ok": h.ok, "collections": h.collections,
                "embedding_provider": h.embedding_provider}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


@router.get("/health", response_model=Health)
async def health() -> Health:
    services = {
        "mongo": await ping_mongo(),
        "redis": await ping_redis(),
        "chroma": _ping_chroma(),
    }
    core_ok = all(services[k] for k in ("mongo", "redis"))
    info = llm_info()
    return Health(
        status="ok" if core_ok else "degraded",
        services=services,
        ai_configured=info["configured"],
        ai_provider=info["provider"],
        ai_model=info["model"],
    )


@router.get("/health/live")
async def live() -> dict:
    return {"status": "alive"}
