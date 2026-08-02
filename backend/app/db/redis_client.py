"""Redis (async) — cache, pub/sub for websocket fan-out, transient state."""

from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.REDIS_URL, encoding="utf-8", decode_responses=True
        )
    return _redis


async def ping_redis() -> bool:
    try:
        return bool(await get_redis().ping())
    except Exception as e:  # noqa: BLE001
        log.warning("Redis ping failed: %s", e)
        return False


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
