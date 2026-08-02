"""
AInvest Platform — FastAPI application entrypoint.

Single local user — no auth. Boots resiliently: each backing service (Mongo,
Redis, Chroma) is initialised best-effort so the API comes up even if one
dependency is still starting. /health reports the true state of each.
"""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analysis_ws_router, api_router
from app.api.ws import redis_subscriber, router as ws_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging

setup_logging()
log = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting %s (env=%s)", settings.APP_NAME, settings.ENV)

    # Initialise Mongo indexes — best effort.
    from app.db.mongo import init_mongo
    with contextlib.suppress(Exception):
        await init_mongo()

    # Ensure all ChromaDB memory collections exist — best effort.
    from app.ai_engine.memory import get_memory_manager
    with contextlib.suppress(Exception):
        get_memory_manager().ensure_ready()

    # Start the Redis→WebSocket relay.
    sub_task = asyncio.create_task(redis_subscriber())

    from app.pipeline.llm import llm_info
    info = llm_info()
    if not info["configured"]:
        log.warning(
            "AI provider '%s' has no key configured (%s) — analysis endpoints "
            "will return a clear error until you set it in .env.",
            info["provider"], info["detail"],
        )
    else:
        log.info("AI provider: %s (%s) — %s", info["provider"], info["model"], info["detail"])

    try:
        yield
    finally:
        sub_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sub_task
        from app.db.redis_client import close_redis
        with contextlib.suppress(Exception):
            await close_redis()
        log.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Local-only, no-auth app — dev frontend ports drift (3000, 3001, ...) and
    # ad-hoc tools (e.g. a browser-rendered health widget) may hit the API from
    # origins that aren't in the explicit list above. Allow any localhost/
    # 127.0.0.1 origin on any port so CORS stops being a recurring blocker.
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
app.include_router(ws_router)  # /ws (unversioned)
app.include_router(analysis_ws_router)  # /ws/analysis/{id}


@app.get("/")
async def root() -> dict:
    from app.pipeline.llm import llm_info

    return {
        "name": settings.APP_NAME,
        "status": "running",
        "docs": "/docs",
        "health": f"{settings.API_V1_PREFIX}/health",
        "ai_configured": llm_info()["configured"],
    }
