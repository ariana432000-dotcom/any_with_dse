"""
Memory routes — read/inspect the ChromaDB memory layer via MemoryManager.

No endpoint touches ChromaDB directly; every call goes through the injected
MemoryManager dependency. Single local user — no auth guard.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.ai_engine.memory import MemoryManager, get_memory_manager
from app.ai_engine.memory.schemas import (
    Collection,
    MemoryHealth,
    MemoryRecord,
    RetrievalQuery,
    RetrievedMemory,
)

router = APIRouter(prefix="/memory", tags=["memory"])


def mm() -> MemoryManager:
    return get_memory_manager()


@router.get("/health", response_model=MemoryHealth)
async def memory_health(manager: MemoryManager = Depends(mm)) -> MemoryHealth:
    return manager.health_check()


@router.get("/collections")
async def list_collections(manager: MemoryManager = Depends(mm)) -> dict:
    return {"collections": manager.list_collections()}


@router.post("/search", response_model=list[RetrievedMemory])
async def search_memory(
    query: RetrievalQuery,
    manager: MemoryManager = Depends(mm),
) -> list[RetrievedMemory]:
    return manager.retrieve_memory(query)


@router.get("/{collection}/recent", response_model=list[RetrievedMemory])
async def recent_memory(
    collection: Collection,
    limit: int = Query(10, ge=1, le=100),
    ticker: str | None = None,
    manager: MemoryManager = Depends(mm),
) -> list[RetrievedMemory]:
    return manager.retrieve_recent(collection, limit=limit, ticker=ticker)


@router.get("/{collection}/{memory_id}", response_model=MemoryRecord)
async def get_memory(
    collection: Collection,
    memory_id: str,
    manager: MemoryManager = Depends(mm),
) -> MemoryRecord:
    rec = manager.get_memory(collection, memory_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return rec


@router.patch("/{collection}/{memory_id}/outcome")
async def update_outcome(
    collection: Collection,
    memory_id: str,
    outcome: str,
    experience_score: float | None = None,
    manager: MemoryManager = Depends(mm),
) -> dict:
    ok = manager.update_outcome(collection, memory_id, outcome, experience_score)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"updated": True, "memory_id": memory_id, "outcome": outcome}


@router.delete("/{collection}/{memory_id}")
async def delete_memory(
    collection: Collection,
    memory_id: str,
    manager: MemoryManager = Depends(mm),
) -> dict:
    manager.delete_memory(collection, memory_id)
    return {"deleted": True, "memory_id": memory_id}
