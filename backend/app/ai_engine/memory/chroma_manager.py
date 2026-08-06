"""
ChromaManager — sole owner of the persistent ChromaDB client and collections.

Responsibilities (Single Responsibility Principle):
  * open ONE persistent client at the .env-configured path (never in-memory),
    creating the directory/database automatically if absent;
  * lazily create/get each of the eight independent collections, wired to the
    configured embedding function;
  * expose low-level collection access to the storage/retrieval layers only.

Nothing above this class constructs a Chroma client. Business code talks to
MemoryManager, which talks to storage/retrieval, which talk to this.
"""

from __future__ import annotations

import os
import threading

from app.ai_engine.memory.embeddings import get_embedding_function, get_provider
from app.ai_engine.memory.schemas import Collection
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


class ChromaManager:
    _instance: "ChromaManager | None" = None
    _lock = threading.Lock()

    def __init__(self, path: str | None = None) -> None:
        self.path = path or settings.CHROMA_DB_PATH
        self._client = None
        self._collections: dict[str, object] = {}
        self._ef = None

    # -- singleton ----------------------------------------------------------
    @classmethod
    def instance(cls) -> "ChromaManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # -- client -------------------------------------------------------------
    @property
    def client(self):
        if self._client is None:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            os.makedirs(self.path, exist_ok=True)  # auto-create db dir
            self._client = chromadb.PersistentClient(
                path=self.path,
                settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
            )
            log.info("ChromaDB persistent client opened at %s", self.path)
        return self._client

    @property
    def embedding_function(self):
        if self._ef is None:
            self._ef = get_embedding_function()
        return self._ef

    # -- collections --------------------------------------------------------
    def get_collection(self, collection: Collection | str):
        """Get-or-create a collection wired to the configured embedding fn."""
        name = collection.value if isinstance(collection, Collection) else str(collection)
        if name not in self._collections:
            self._collections[name] = self.client.get_or_create_collection(
                name=name,
                embedding_function=self.embedding_function,
                metadata={"hnsw:space": "cosine", "managed_by": "MemoryManager"},
            )
            log.debug("collection ready: %s", name)
        return self._collections[name]

    def ensure_all_collections(self) -> list[str]:
        """Create every declared collection up front (startup convenience)."""
        created = []
        for c in Collection:
            self.get_collection(c)
            created.append(c.value)
        log.info("ensured %d collections: %s", len(created), ", ".join(created))
        return created

    def list_collections(self) -> dict[str, int]:
        """Name -> document count for all managed collections."""
        out: dict[str, int] = {}
        for c in Collection:
            try:
                out[c.value] = self.get_collection(c).count()
            except Exception as e:  # noqa: BLE001
                log.warning("count failed for %s: %s", c.value, e)
                out[c.value] = -1
        return out

    def health(self) -> dict:
        try:
            provider = get_provider()
            counts = self.list_collections()
            return {
                "ok": all(v >= 0 for v in counts.values()),
                "path": self.path,
                "embedding_provider": provider.name,
                "embedding_model": provider.model,
                "collections": counts,
            }
        except Exception as e:  # noqa: BLE001
            log.error("Chroma health check failed: %s", e)
            return {
                "ok": False,
                "path": self.path,
                "embedding_provider": settings.EMBEDDING_PROVIDER,
                "embedding_model": "",
                "collections": {},
                "error": str(e),
            }

    def reset(self) -> None:
        """Danger: wipes all collections. Used only by integration tests."""
        self.client.reset()
        self._collections.clear()
