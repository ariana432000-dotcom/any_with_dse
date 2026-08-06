"""
Storage layer — writes MemoryRecords into ChromaDB.

Owns add/upsert/update-metadata/delete for the generic collections. RAEM keeps
its own episodic writer (RAEMMemory.save_episode); this layer handles everything
else and the outcome-update path. Emits the required logs: stored document id,
collection name, latency, errors.
"""

from __future__ import annotations

import time
from typing import Iterable

from app.ai_engine.memory.chroma_manager import ChromaManager
from app.ai_engine.memory.schemas import Collection, MemoryRecord
from app.core.logging import get_logger

log = get_logger(__name__)


class MemoryStorage:
    def __init__(self, manager: ChromaManager | None = None) -> None:
        self._m = manager or ChromaManager.instance()

    def store(self, collection: Collection, record: MemoryRecord) -> str:
        t0 = time.perf_counter()
        payload = record.to_chroma()
        coll = self._m.get_collection(collection)
        coll.upsert(
            ids=[payload["id"]],
            documents=[payload["document"]],
            metadatas=[payload["metadata"]],
        )
        dt = (time.perf_counter() - t0) * 1000
        log.info(
            "stored memory id=%s collection=%s latency=%.1fms",
            payload["id"], collection.value, dt,
        )
        return payload["id"]

    def store_many(self, collection: Collection, records: Iterable[MemoryRecord]) -> list[str]:
        payloads = [r.to_chroma() for r in records]
        if not payloads:
            return []
        t0 = time.perf_counter()
        self._m.get_collection(collection).upsert(
            ids=[p["id"] for p in payloads],
            documents=[p["document"] for p in payloads],
            metadatas=[p["metadata"] for p in payloads],
        )
        dt = (time.perf_counter() - t0) * 1000
        log.info("stored %d memories collection=%s latency=%.1fms",
                 len(payloads), collection.value, dt)
        return [p["id"] for p in payloads]

    def update_metadata(self, collection: Collection, memory_id: str, updates: dict) -> bool:
        """Patch metadata on an existing record (e.g. outcome backfill)."""
        coll = self._m.get_collection(collection)
        existing = coll.get(ids=[memory_id])
        if not existing["ids"]:
            log.warning("update_metadata: id=%s not found in %s", memory_id, collection.value)
            return False
        meta = dict(existing["metadatas"][0])
        meta.update(updates)
        coll.update(ids=[memory_id], metadatas=[meta])
        log.info("updated memory id=%s collection=%s keys=%s",
                 memory_id, collection.value, list(updates))
        return True

    def delete(self, collection: Collection, memory_id: str) -> bool:
        coll = self._m.get_collection(collection)
        coll.delete(ids=[memory_id])
        log.info("deleted memory id=%s collection=%s", memory_id, collection.value)
        return True

    def get(self, collection: Collection, memory_id: str) -> MemoryRecord | None:
        res = self._m.get_collection(collection).get(ids=[memory_id])
        if not res["ids"]:
            return None
        return MemoryRecord.from_chroma(res["documents"][0], res["metadatas"][0])
