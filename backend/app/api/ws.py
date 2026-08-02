"""
WebSocket hub — pushes live updates (quotes, new analyses, signals) to the
dashboard. Fan-out is backed by Redis pub/sub so multiple API workers stay in
sync; any worker can publish and every connected client receives it.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.logging import get_logger
from app.db.redis_client import get_redis

log = get_logger(__name__)
router = APIRouter()

CHANNEL = "ainvest:events"


class ConnectionManager:
    def __init__(self) -> None:
        self.active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)

    async def broadcast(self, message: dict) -> None:
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


async def publish_event(event: dict) -> None:
    """Publish an event to all API workers via Redis (used by workers/services)."""
    try:
        await get_redis().publish(CHANNEL, json.dumps(event))
    except Exception as e:  # noqa: BLE001
        log.debug("publish_event failed: %s", e)


async def redis_subscriber() -> None:
    """Background task: relay Redis pub/sub messages to local websocket clients."""
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(CHANNEL)
    log.info("WebSocket Redis subscriber started")
    try:
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            try:
                await manager.broadcast(json.loads(msg["data"]))
            except Exception:  # noqa: BLE001
                pass
    except asyncio.CancelledError:
        pass
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        await ws.send_json({"type": "connected", "message": "AInvest live stream"})
        while True:
            # Keep the socket open; clients may send ping/subscription messages.
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:  # noqa: BLE001
        manager.disconnect(ws)
