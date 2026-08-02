"""
MemoryManager — the single entry point for all memory operations.

Design:
  * Generic memories (market / conversation / portfolio / research / news /
    execution / agent_reasoning) go through storage + retrieval over ChromaDB.
  * Episodic RAEM memory is DELEGATED to the notebook's `RAEMMemory` (imported
    from app.pipeline.memory) — its experience replay, memory ranking, outcome
    backfill, regime tagging, experience scoring, and context injection are
    reused verbatim, never reimplemented here.

No route, agent, or service touches ChromaDB directly; they all go through an
instance of this class (see `get_memory_manager()` for the shared singleton and
FastAPI dependency).

Dependency injection: storage, retrieval, chroma manager and the RAEM engine can
all be injected (defaults wire the production singletons), which keeps the class
unit-testable.
"""

from __future__ import annotations

from typing import Any

from app.ai_engine.memory.chroma_manager import ChromaManager
from app.ai_engine.memory.retrieval import MemoryRetrieval
from app.ai_engine.memory.schemas import (
    Collection,
    MemoryHealth,
    MemoryRecord,
    RetrievalQuery,
    RetrievedMemory,
)
from app.ai_engine.memory.storage import MemoryStorage
from app.core.logging import get_logger

log = get_logger(__name__)


class MemoryManager:
    def __init__(
        self,
        manager: ChromaManager | None = None,
        storage: MemoryStorage | None = None,
        retrieval: MemoryRetrieval | None = None,
        raem: Any | None = None,
    ) -> None:
        self._chroma = manager or ChromaManager.instance()
        self._storage = storage or MemoryStorage(self._chroma)
        self._retrieval = retrieval or MemoryRetrieval(self._chroma)
        self._raem = raem  # lazily created RAEMMemory (see .raem)

    # ------------------------------------------------------------------ RAEM
    @property
    def raem(self):
        """The notebook's RAEM engine (episodic memory). Reused, not rewritten."""
        if self._raem is None:
            from app.pipeline.memory import RAEMMemory
            self._raem = RAEMMemory()
        return self._raem

    # ----------------------------------------------------------------- store
    def store_memory(self, collection: Collection | str, record: MemoryRecord) -> str:
        """Store any memory. Returns the stored document id."""
        collection = Collection(collection) if not isinstance(collection, Collection) else collection
        return self._storage.store(collection, record)

    def store_many(self, collection: Collection | str, records: list[MemoryRecord]) -> list[str]:
        collection = Collection(collection) if not isinstance(collection, Collection) else collection
        return self._storage.store_many(collection, records)

    # -------------------------------------------------------------- retrieve
    def retrieve_memory(self, query: RetrievalQuery) -> list[RetrievedMemory]:
        """General retrieval with the full filter set (semantic if query.text set)."""
        return self._retrieval.search(query)

    def retrieve_recent(self, collection: Collection | str, limit: int = 10,
                        ticker: str | None = None) -> list[RetrievedMemory]:
        collection = Collection(collection) if not isinstance(collection, Collection) else collection
        return self._retrieval.recent(collection, limit=limit, ticker=ticker)

    def retrieve_similar(self, text: str, collection: Collection | str = Collection.EPISODIC,
                        top_k: int = 5, similarity_threshold: float | None = None,
                        **filters: Any) -> list[RetrievedMemory]:
        collection = Collection(collection) if not isinstance(collection, Collection) else collection
        q = RetrievalQuery(
            text=text, collection=collection, top_k=top_k,
            similarity_threshold=similarity_threshold, **filters,
        )
        return self._retrieval.search(q)

    def retrieve_by_ticker(self, ticker: str, collection: Collection | str = Collection.EPISODIC,
                          top_k: int = 10, text: str | None = None) -> list[RetrievedMemory]:
        collection = Collection(collection) if not isinstance(collection, Collection) else collection
        return self._retrieval.search(RetrievalQuery(
            text=text, collection=collection, top_k=top_k, ticker=ticker.upper(),
        ))

    def retrieve_by_regime(self, market_regime: str,
                          collection: Collection | str = Collection.EPISODIC,
                          top_k: int = 10, text: str | None = None,
                          ticker: str | None = None) -> list[RetrievedMemory]:
        collection = Collection(collection) if not isinstance(collection, Collection) else collection
        return self._retrieval.search(RetrievalQuery(
            text=text, collection=collection, top_k=top_k,
            market_regime=market_regime, ticker=ticker,
        ))

    def retrieve_by_tags(self, tags: list[str],
                        collection: Collection | str = Collection.EPISODIC,
                        top_k: int = 10, text: str | None = None) -> list[RetrievedMemory]:
        collection = Collection(collection) if not isinstance(collection, Collection) else collection
        return self._retrieval.search(RetrievalQuery(
            text=text, collection=collection, top_k=top_k, tags=tags,
        ))

    # ---------------------------------------------------------------- update
    def update_outcome(self, collection: Collection | str, memory_id: str,
                      outcome: str, experience_score: float | None = None,
                      extra: dict[str, Any] | None = None) -> bool:
        """Patch the outcome (+ optional experience score) on a stored memory."""
        collection = Collection(collection) if not isinstance(collection, Collection) else collection
        updates: dict[str, Any] = {"outcome": outcome}
        if experience_score is not None:
            updates["experience_score"] = float(experience_score)
        if extra:
            updates.update(extra)
        return self._storage.update_metadata(collection, memory_id, updates)

    # ---------------------------------------------------------------- delete
    def delete_memory(self, collection: Collection | str, memory_id: str) -> bool:
        collection = Collection(collection) if not isinstance(collection, Collection) else collection
        return self._storage.delete(collection, memory_id)

    def get_memory(self, collection: Collection | str, memory_id: str) -> MemoryRecord | None:
        collection = Collection(collection) if not isinstance(collection, Collection) else collection
        return self._storage.get(collection, memory_id)

    # ---------------------------------------------------------------- admin
    def list_collections(self) -> dict[str, int]:
        return self._chroma.list_collections()

    def health_check(self) -> MemoryHealth:
        h = self._chroma.health()
        return MemoryHealth(**h)

    def ensure_ready(self) -> list[str]:
        """Create all collections up front (called on startup)."""
        return self._chroma.ensure_all_collections()


# --------------------------------------------------------------------------
# Shared singleton + FastAPI dependency
# --------------------------------------------------------------------------
_manager_singleton: MemoryManager | None = None


def get_memory_manager() -> MemoryManager:
    global _manager_singleton
    if _manager_singleton is None:
        _manager_singleton = MemoryManager()
    return _manager_singleton
