"""
Integration tests for the ChromaDB memory layer.

These use a REAL persistent ChromaDB (in a temp dir) but a deterministic, offline
fake embedding provider so the suite runs without Ollama/OpenAI. They cover:
store, retrieve, semantic search, ticker filtering, outcome update, RAEM
retrieval, and persistence across a simulated restart (new client, same path).

Run:  cd backend && pytest tests/test_memory_integration.py -v
"""

from __future__ import annotations

import hashlib
import os
import tempfile

import pytest

# ---- offline fake embedding provider (registered before anything connects) ----
from app.ai_engine.memory import embeddings as emb


class _FakeProvider(emb.EmbeddingProvider):
    name = "fake"

    def __init__(self, dim: int = 64) -> None:
        super().__init__("fake-model")
        self.dim = dim

    def embed(self, texts):
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            # deterministic pseudo-vector in [0,1], length dim
            vec = [((h[i % len(h)] + i) % 97) / 97.0 for i in range(self.dim)]
            out.append(vec)
        return out


@pytest.fixture(scope="module")
def tmp_chroma_path():
    d = tempfile.mkdtemp(prefix="chroma_test_")
    yield d


@pytest.fixture()
def manager(tmp_chroma_path, monkeypatch):
    """Fresh ChromaManager bound to a temp path with the fake embedder."""
    from app.ai_engine.memory.chroma_manager import ChromaManager

    emb._provider_singleton = _FakeProvider()
    monkeypatch.setattr(emb, "get_provider", lambda: emb._provider_singleton)
    monkeypatch.setattr(emb, "get_embedding_function",
                        lambda: emb._provider_singleton.as_chroma_function())

    ChromaManager._instance = None
    mgr = ChromaManager(path=tmp_chroma_path)
    ChromaManager._instance = mgr
    return mgr


@pytest.fixture()
def mm(manager):
    from app.ai_engine.memory import MemoryManager
    from app.ai_engine.memory.storage import MemoryStorage
    from app.ai_engine.memory.retrieval import MemoryRetrieval

    return MemoryManager(
        manager=manager,
        storage=MemoryStorage(manager),
        retrieval=MemoryRetrieval(manager),
    )


def _rec(**kw):
    from app.ai_engine.memory.schemas import MemoryRecord
    base = dict(ticker="AAPL", agent_name="MarketAnalyst", summary="strong uptrend",
                reasoning="RSI 61, MACD positive", decision="BUY", confidence=0.72,
                market_regime="TRENDING_BULL", tags=["AAPL", "momentum"], source="test")
    base.update(kw)
    return MemoryRecord(**base)


# ---------------------------------------------------------------- tests
def test_store_and_get(mm):
    from app.ai_engine.memory.schemas import Collection
    mid = mm.store_memory(Collection.MARKET, _rec())
    assert mid
    got = mm.get_memory(Collection.MARKET, mid)
    assert got is not None
    assert got.ticker == "AAPL"
    assert got.decision == "BUY"


def test_ensure_all_collections(manager):
    from app.ai_engine.memory.schemas import Collection
    created = manager.ensure_all_collections()
    assert set(created) == set(Collection.values())
    assert len(created) == 8


def test_semantic_search(mm):
    from app.ai_engine.memory.schemas import Collection
    mm.store_memory(Collection.RESEARCH, _rec(summary="bullish breakout above resistance",
                                              reasoning="volume surge", decision="BUY"))
    mm.store_memory(Collection.RESEARCH, _rec(summary="bearish breakdown", ticker="TSLA",
                                              reasoning="support lost", decision="SELL"))
    hits = mm.retrieve_similar("breakout bullish momentum", collection=Collection.RESEARCH, top_k=5)
    assert hits, "expected at least one semantic hit"
    # similarity is populated for text queries
    assert hits[0].similarity is not None


def test_ticker_filter(mm):
    from app.ai_engine.memory.schemas import Collection
    mm.store_memory(Collection.MARKET, _rec(ticker="AAPL"))
    mm.store_memory(Collection.MARKET, _rec(ticker="MSFT", summary="msft note"))
    aapl = mm.retrieve_by_ticker("AAPL", collection=Collection.MARKET, top_k=20)
    assert aapl
    assert all(r.record.ticker == "AAPL" for r in aapl)


def test_regime_filter(mm):
    from app.ai_engine.memory.schemas import Collection
    mm.store_memory(Collection.MARKET, _rec(market_regime="OVERBOUGHT", summary="ob"))
    mm.store_memory(Collection.MARKET, _rec(market_regime="TRENDING_BULL", summary="tb"))
    res = mm.retrieve_by_regime("OVERBOUGHT", collection=Collection.MARKET, top_k=20)
    assert res
    assert all(r.record.market_regime == "OVERBOUGHT" for r in res)


def test_outcome_update_and_experience(mm):
    from app.ai_engine.memory.schemas import Collection
    mid = mm.store_memory(Collection.EXECUTION, _rec(outcome="PENDING"))
    ok = mm.update_outcome(Collection.EXECUTION, mid, "WIN", experience_score=0.9)
    assert ok
    got = mm.get_memory(Collection.EXECUTION, mid)
    assert got.outcome == "WIN"
    assert abs(got.experience_score - 0.9) < 1e-6


def test_delete(mm):
    from app.ai_engine.memory.schemas import Collection
    mid = mm.store_memory(Collection.NEWS, _rec(summary="to delete"))
    assert mm.get_memory(Collection.NEWS, mid) is not None
    mm.delete_memory(Collection.NEWS, mid)
    assert mm.get_memory(Collection.NEWS, mid) is None


def test_health_and_list(mm):
    h = mm.health_check()
    assert h.ok is True
    assert h.embedding_provider == "fake"
    cols = mm.list_collections()
    assert "episodic_memory" in cols


def test_raem_uses_shared_client(mm, manager):
    """The notebook's RAEMMemory should bind to the SAME persistent client."""
    from app.pipeline.memory import RAEMMemory
    r = RAEMMemory()
    r.connect()
    # episodic collection is the platform's EPISODIC collection
    from app.ai_engine.memory.schemas import Collection
    assert r.episodic.name == Collection.EPISODIC.value
    # a save via RAEM should be retrievable via MemoryManager
    saved = r.save_episode(
        "AAPL", "2026-06-19",
        indicators={"rsi": 61, "macd": 1.2, "close_50_sma": 220, "boll_ub": 235, "boll_lb": 210},
        fund_metrics={"pe_ratio": "31", "eps_ttm": "7.4", "market_cap": "3.5T"},
        news_metrics={"overall_sentiment": "POSITIVE", "positive_count": 3, "negative_count": 1, "neutral_count": 2},
        sentiment_metrics={"score": "7", "overall": "BULLISH"},
        final_decision_text="Final Decision: BUY with confidence.",
        stock_data="Date,Open,High,Low,Close,Volume\n2026-06-19,230,236,229,235,40000000",
    )
    assert saved["signal"] == "BUY"
    assert saved["regime"] in ("TRENDING_BULL", "TRENDING_BULL_HIGH_VOL")


def test_persistence_after_restart(mm, manager, tmp_chroma_path, monkeypatch):
    """Data written by one client is readable by a brand-new client, same path."""
    from app.ai_engine.memory.schemas import Collection
    from app.ai_engine.memory.chroma_manager import ChromaManager
    from app.ai_engine.memory import MemoryManager

    mid = mm.store_memory(Collection.PORTFOLIO, _rec(summary="persist me", ticker="NVDA"))

    # Simulate a restart: drop the client, build a fresh manager on the same path.
    ChromaManager._instance = None
    fresh_mgr = ChromaManager(path=tmp_chroma_path)
    ChromaManager._instance = fresh_mgr
    fresh_mm = MemoryManager(manager=fresh_mgr)

    got = fresh_mm.get_memory(Collection.PORTFOLIO, mid)
    assert got is not None
    assert got.ticker == "NVDA"
    assert got.summary == "persist me"
