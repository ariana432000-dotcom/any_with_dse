"""
Retrieval layer — reads/searches ChromaDB and maps rows back to MemoryRecords.

Supports the full retrieval spec: top-k, semantic similarity, ticker/date/agent/
regime filters, similarity threshold, and a raw metadata-filter escape hatch.
Cosine distance from Chroma is converted to a 0..1 similarity for thresholding
and ranking. Emits the required logs: similarity score, retrieval latency,
collection name, errors.
"""

from __future__ import annotations

import time
from typing import Any

from app.ai_engine.memory.chroma_manager import ChromaManager
from app.ai_engine.memory.schemas import (
    Collection,
    MemoryRecord,
    RetrievalQuery,
    RetrievedMemory,
)
from app.core.logging import get_logger

log = get_logger(__name__)

_SENTINEL = "__none__"


def _similarity_from_distance(distance: float | None) -> float | None:
    if distance is None:
        return None
    # Chroma cosine "distance" is 1 - cosine_similarity → similarity = 1 - distance
    return max(0.0, min(1.0, 1.0 - float(distance)))


class MemoryRetrieval:
    def __init__(self, manager: ChromaManager | None = None) -> None:
        self._m = manager or ChromaManager.instance()

    # -- filter builder -----------------------------------------------------
    @staticmethod
    def _build_where(q: RetrievalQuery) -> dict[str, Any] | None:
        clauses: list[dict[str, Any]] = []
        if q.ticker:
            clauses.append({"ticker": q.ticker.upper()})
        if q.agent_name:
            clauses.append({"agent_name": q.agent_name})
        if q.market_regime:
            clauses.append({"market_regime": q.market_regime})
        if q.date_from:
            clauses.append({"timestamp": {"$gte": q.date_from}})
        if q.date_to:
            clauses.append({"timestamp": {"$lte": q.date_to}})
        if q.tags:
            # tags are stored as a delimited string; match any requested tag
            for tag in q.tags:
                clauses.append({"tags": {"$contains": tag}}) if False else None
            # Chroma metadata doesn't support substring on arbitrary strings in
            # all versions; tag filtering is applied post-hoc in `_tag_ok`.
        if q.where:
            clauses.append(q.where)
        if not clauses:
            return None
        return clauses[0] if len(clauses) == 1 else {"$and": clauses}

    @staticmethod
    def _tag_ok(record: MemoryRecord, tags: list[str] | None) -> bool:
        if not tags:
            return True
        have = set(record.tags)
        return any(t in have for t in tags)

    # -- semantic search ----------------------------------------------------
    def search(self, q: RetrievalQuery) -> list[RetrievedMemory]:
        t0 = time.perf_counter()
        coll = self._m.get_collection(q.collection)
        where = self._build_where(q)
        # Over-fetch a little so post-hoc tag/threshold filtering still yields top_k.
        n = max(q.top_k * 3, q.top_k) if (q.tags or q.similarity_threshold) else q.top_k

        results: list[RetrievedMemory] = []
        try:
            if q.text:
                # Compute the query embedding explicitly via the configured
                # provider, then pass query_embeddings — this avoids relying on
                # Chroma's internal embed_query signature (which varies across
                # versions) and keeps provider selection in one place.
                from app.ai_engine.memory.embeddings import get_provider
                qvec = get_provider().embed_one(q.text)
                raw = coll.query(
                    query_embeddings=[qvec],
                    n_results=n,
                    where=where,
                    include=["documents", "metadatas", "distances"],
                )
                ids = raw.get("ids", [[]])[0]
                docs = raw.get("documents", [[]])[0]
                metas = raw.get("metadatas", [[]])[0]
                dists = raw.get("distances", [[]])[0]
                for i in range(len(ids)):
                    rec = MemoryRecord.from_chroma(docs[i], metas[i])
                    dist = dists[i] if i < len(dists) else None
                    sim = _similarity_from_distance(dist)
                    results.append(RetrievedMemory(record=rec, similarity=sim, distance=dist))
            else:
                # No query text → metadata-only fetch (recency/filters).
                raw = coll.get(where=where, limit=n, include=["documents", "metadatas"])
                for i in range(len(raw.get("ids", []))):
                    rec = MemoryRecord.from_chroma(raw["documents"][i], raw["metadatas"][i])
                    results.append(RetrievedMemory(record=rec, similarity=None, distance=None))
        except Exception as e:  # noqa: BLE001
            log.error("retrieval failed collection=%s: %s", q.collection.value, e)
            return []

        # post-hoc filters: tags + similarity threshold
        filtered = [r for r in results if self._tag_ok(r.record, q.tags)]
        if q.similarity_threshold is not None:
            filtered = [
                r for r in filtered
                if r.similarity is not None and r.similarity >= q.similarity_threshold
            ]
        filtered = filtered[: q.top_k]

        dt = (time.perf_counter() - t0) * 1000
        top_sim = filtered[0].similarity if filtered and filtered[0].similarity is not None else None
        log.info(
            "retrieved %d/%d collection=%s top_sim=%s latency=%.1fms",
            len(filtered), len(results), q.collection.value,
            f"{top_sim:.3f}" if top_sim is not None else "n/a", dt,
        )
        return filtered

    # -- convenience --------------------------------------------------------
    def recent(self, collection: Collection, limit: int = 10,
               ticker: str | None = None) -> list[RetrievedMemory]:
        res = self.search(RetrievalQuery(
            text=None, collection=collection, top_k=limit * 4, ticker=ticker,
        ))
        res.sort(key=lambda r: r.record.timestamp, reverse=True)
        return res[:limit]
