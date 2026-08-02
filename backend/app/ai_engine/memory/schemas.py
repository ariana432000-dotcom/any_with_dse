"""
Memory schemas — the canonical shape of every record stored in ChromaDB.

Chroma stores three parallel arrays per item: `documents` (the text that gets
embedded), `metadatas` (flat scalar dicts used for filtering), and `ids`. A
`MemoryRecord` is our rich domain object; `to_chroma()` flattens it into exactly
that shape, and `from_chroma()` reconstructs it. Chroma metadata values must be
str/int/float/bool, so lists (tags) are serialized to a delimited string.

This schema is a superset that stays compatible with the notebook's existing
episodic metadata (company/trade_date/regime/final_signal/outcome_*), so RAEM
episodes and generic memories live in the same store without conflict.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Collection(str, Enum):
    """The eight independent memory collections."""

    EPISODIC = "episodic_memory"
    MARKET = "market_memory"
    CONVERSATION = "conversation_memory"
    PORTFOLIO = "portfolio_memory"
    RESEARCH = "research_memory"
    NEWS = "news_memory"
    EXECUTION = "execution_history"
    AGENT_REASONING = "agent_reasoning"

    @classmethod
    def values(cls) -> list[str]:
        return [c.value for c in cls]


_TAG_SEP = "|"
_SENTINEL = "__none__"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryRecord(BaseModel):
    """One memory. `document` is embedded; the rest becomes filterable metadata."""

    memory_id: str = ""
    ticker: str = ""
    timestamp: str = Field(default_factory=_utcnow_iso)
    market_regime: str = ""
    agent_name: str = ""
    summary: str = ""
    reasoning: str = ""
    decision: str = ""
    confidence: float = 0.0
    risk: str = ""
    # `embedding` is produced by the embedding provider at store time; kept
    # optional here so callers may pass a precomputed vector.
    embedding: list[float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    source: str = ""
    version: str = "1.0"
    outcome: str = "PENDING"
    experience_score: float = 0.0

    # --- identity -----------------------------------------------------------
    def ensure_id(self) -> str:
        if not self.memory_id:
            basis = f"{self.ticker}|{self.agent_name}|{self.timestamp}|{self.summary[:64]}"
            self.memory_id = hashlib.md5(basis.encode()).hexdigest()[:20]
        return self.memory_id

    # --- document (embedded text) ------------------------------------------
    def to_document(self) -> str:
        """Human-readable, embedding-friendly text built from the salient fields."""
        parts = []
        if self.ticker:
            parts.append(f"Ticker: {self.ticker}")
        if self.market_regime:
            parts.append(f"Regime: {self.market_regime}")
        if self.agent_name:
            parts.append(f"Agent: {self.agent_name}")
        if self.decision:
            parts.append(f"Decision: {self.decision}")
        if self.summary:
            parts.append(f"Summary: {self.summary}")
        if self.reasoning:
            parts.append(f"Reasoning: {self.reasoning}")
        return "\n".join(parts) if parts else (self.summary or self.reasoning or self.ticker)

    # --- chroma mapping -----------------------------------------------------
    def to_chroma(self) -> dict[str, Any]:
        """Return {id, document, metadata} ready for a Chroma add/upsert call."""
        self.ensure_id()
        meta: dict[str, Any] = {
            "memory_id": self.memory_id,
            "ticker": self.ticker or _SENTINEL,
            "timestamp": self.timestamp,
            "market_regime": self.market_regime or _SENTINEL,
            "agent_name": self.agent_name or _SENTINEL,
            "summary": self.summary[:1000],
            "decision": self.decision or _SENTINEL,
            "confidence": float(self.confidence),
            "risk": self.risk or _SENTINEL,
            "source": self.source or _SENTINEL,
            "version": self.version,
            "outcome": self.outcome or "PENDING",
            "experience_score": float(self.experience_score),
            "tags": _TAG_SEP.join(self.tags) if self.tags else _SENTINEL,
        }
        # Flatten user metadata (scalar values only; Chroma rejects nested types).
        for k, v in (self.metadata or {}).items():
            if isinstance(v, (str, int, float, bool)):
                meta[f"m_{k}"] = v
            else:
                meta[f"m_{k}"] = json.dumps(v, default=str)
        return {"id": self.memory_id, "document": self.to_document(), "metadata": meta}

    @classmethod
    def from_chroma(cls, doc: str, meta: dict[str, Any]) -> "MemoryRecord":
        def clean(key: str, default: Any = "") -> Any:
            v = meta.get(key, default)
            return default if v == _SENTINEL else v

        tags_raw = meta.get("tags", "")
        tags = [] if tags_raw in ("", _SENTINEL) else str(tags_raw).split(_TAG_SEP)
        user_meta = {
            k[2:]: v for k, v in meta.items() if k.startswith("m_")
        }
        return cls(
            memory_id=meta.get("memory_id", ""),
            ticker=clean("ticker"),
            timestamp=meta.get("timestamp", ""),
            market_regime=clean("market_regime"),
            agent_name=clean("agent_name"),
            summary=meta.get("summary", ""),
            reasoning=doc or "",
            decision=clean("decision"),
            confidence=float(meta.get("confidence", 0.0) or 0.0),
            risk=clean("risk"),
            metadata=user_meta,
            tags=tags,
            source=clean("source"),
            version=meta.get("version", "1.0"),
            outcome=meta.get("outcome", "PENDING"),
            experience_score=float(meta.get("experience_score", 0.0) or 0.0),
        )


class RetrievalQuery(BaseModel):
    """Parameters for a memory retrieval (all filters optional)."""

    text: str | None = None
    collection: Collection = Collection.EPISODIC
    top_k: int = 5
    ticker: str | None = None
    agent_name: str | None = None
    market_regime: str | None = None
    tags: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None
    similarity_threshold: float | None = None  # 0..1, keep results at/above
    where: dict[str, Any] | None = None         # raw metadata filter escape hatch


class RetrievedMemory(BaseModel):
    record: MemoryRecord
    similarity: float | None = None
    distance: float | None = None


class MemoryHealth(BaseModel):
    ok: bool
    path: str
    embedding_provider: str
    embedding_model: str
    collections: dict[str, int] = {}
    error: str | None = None
