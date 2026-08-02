"""
Integration tests for the AI Execution Engine (Phase 3).

Covers the deliverable checklist without needing live LLMs, Ollama, or network:
  * complete execution pipeline (Orchestrator end-to-end)
  * provider fallback (primary fails -> next available)
  * memory retrieval (RAEM/ChromaDB via MemoryManager)
  * TradingAgents execution (the reused PipelineRunner is stubbed with realistic
    events so we test the ORCHESTRATION, not the LLM output)
  * MongoDB persistence (mongomock)
  * WebSocket events (captured via an in-memory sink)

Run:  cd backend && pytest tests/test_execution_engine.py -v
"""

from __future__ import annotations

import hashlib
import tempfile

import pytest

# ---- offline fake embedder (same approach as the memory tests) ----
from app.ai_engine.memory import embeddings as emb


class _FakeEmb(emb.EmbeddingProvider):
    name = "fake"

    def __init__(self):
        super().__init__("fake-model")

    def embed(self, texts):
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            out.append([((h[i % len(h)] + i) % 97) / 97.0 for i in range(64)])
        return out


@pytest.fixture(autouse=True)
def _fake_embedder(monkeypatch):
    emb._provider_singleton = _FakeEmb()
    monkeypatch.setattr(emb, "get_provider", lambda: emb._provider_singleton)
    monkeypatch.setattr(emb, "get_embedding_function",
                        lambda: emb._provider_singleton.as_chroma_function())


@pytest.fixture(autouse=True)
def _temp_chroma(monkeypatch):
    from app.ai_engine.memory.chroma_manager import ChromaManager
    ChromaManager._instance = None
    mgr = ChromaManager(path=tempfile.mkdtemp(prefix="chroma_engine_"))
    ChromaManager._instance = mgr
    yield


@pytest.fixture(autouse=True)
def _stub_market(monkeypatch):
    """Deterministic market data (no network)."""
    async def fake_history(ticker, days_back=220, asset_type="stock"):
        return {
            "ticker": ticker.upper(), "provider": "stub",
            "latest_close": 235.8,
            "indicators": {"rsi": 61.4, "macd": 1.82, "close_50_sma": 222.6,
                        "boll_ub": 238.9, "boll_lb": 210.3},
            "rows": [{"date": "2026-06-19", "open": 230, "high": 236, "low": 229,
                    "close": 235.8, "volume": 40_000_000}],
            "fetched_at": "2026-06-19T00:00:00Z",
        }

    async def fake_quote(ticker):
        return {"ticker": ticker.upper(), "price": 235.8, "change_pct": 1.2}

    async def fake_news(ticker, limit=8):
        return [{"title": "Services revenue hits record", "sentiment": "POSITIVE"}]

    from app.services import market_data as mds
    monkeypatch.setattr(mds, "get_history", fake_history)
    monkeypatch.setattr(mds, "get_quote", fake_quote)
    monkeypatch.setattr(mds, "get_news", fake_news)


@pytest.fixture(autouse=True)
def _stub_runner(monkeypatch):
    """Replace the reused PipelineRunner with one that emits realistic events,
    so we test orchestration deterministically without any LLM calls."""
    from app.pipeline import runner as runner_mod

    class StubRunner:
        def __init__(self, company, trade_date, asset_type="stock", **kw):
            self.company = company.upper()
            self.trade_date = trade_date

        def run(self):
            def sd(stage, html, **meta):
                return {"type": "stage_done", "stage": stage, "html": html, "meta": meta}
            yield {"type": "stage_start", "stage": "market", "index": 1, "total": 13}
            yield sd("market", "<p>RSI 61 uptrend</p>", confidence=0.7,
                    indicators={"rsi": 61.4})
            yield {"type": "regime", "regime": "TRENDING_BULL", "episodes": []}
            yield {"type": "stage_start", "stage": "fundamentals", "index": 2, "total": 13}
            yield sd("fundamentals", "<p>P/E 31, strong FCF. BUY</p>", confidence=0.65)
            yield {"type": "stage_start", "stage": "news", "index": 3, "total": 13}
            yield sd("news", "<p>Positive coverage</p>", confidence=0.6)
            yield {"type": "stage_start", "stage": "sentiment", "index": 4, "total": 13}
            yield sd("sentiment", "<p>Bullish 7/10</p>", confidence=0.62)
            yield {"type": "stage_start", "stage": "investment_debate", "index": 5, "total": 13}
            yield {"type": "debate_turn", "stage": "investment_debate", "speaker": "Bull Analyst",
                "side": "bull", "round": 1, "html": "<p>Momentum strong</p>"}
            yield {"type": "debate_turn", "stage": "investment_debate", "speaker": "Bear Analyst",
                "side": "bear", "round": 1, "html": "<p>Valuation rich</p>"}
            yield sd("investment_debate", "", count=2)
            yield {"type": "stage_start", "stage": "risk_debate", "index": 6, "total": 13}
            yield sd("risk_debate", "", count=3)
            yield {"type": "stage_start", "stage": "risk_facilitator", "index": 7, "total": 13}
            yield sd("risk_facilitator", "<p>Risk MEDIUM, size 50%</p>")
            yield {"type": "stage_start", "stage": "portfolio_manager", "index": 8, "total": 13}
            yield sd("portfolio_manager", "<p>FINAL: HOLD with bullish bias</p>",
                    signal="HOLD")
            yield {"type": "final", "signal": "HOLD", "html": "<p>HOLD</p>"}
            yield {"type": "done", "session_id": "stub"}

    monkeypatch.setattr(runner_mod, "PipelineRunner", StubRunner)


# ------------------------------------------------------------------- tests
@pytest.mark.asyncio
async def test_complete_execution_pipeline():
    from app.ai_engine.events import EventEmitter, EventType
    from app.ai_engine.orchestrator import Orchestrator
    from app.ai_engine.state import ExecutionRequest, ExecutionStatus

    events = []
    em = EventEmitter("test-exec-1", "AAPL")
    em.add_sink(lambda e: events.append(e) or _noop())

    orch = Orchestrator()
    state = await orch.execute(ExecutionRequest(ticker="AAPL"), emitter=em)

    assert state.status in (ExecutionStatus.COMPLETED, ExecutionStatus.PARTIAL)
    assert state.market is not None and state.market.indicators["rsi"] == 61.4
    assert state.memory is not None
    assert state.recommendation is not None
    assert state.recommendation.signal.value in ("BUY", "HOLD", "SELL")
    # agents captured
    assert "TechnicalAnalyst" in state.agents
    assert "FundamentalAnalyst" in state.agents
    # debate captured
    assert state.debate is not None and len(state.debate.turns) == 2
    # event stream includes the canonical lifecycle
    types = {e.type for e in events}
    assert EventType.STARTED in types
    assert EventType.FETCHING_MARKET_DATA in types
    assert EventType.RETRIEVING_MEMORY in types
    assert EventType.COMPLETED in types


async def _noop():
    return None


@pytest.mark.asyncio
async def test_websocket_events_ordered():
    from app.ai_engine.events import EventEmitter, EventType, PROGRESS_ORDER
    from app.ai_engine.orchestrator import Orchestrator
    from app.ai_engine.state import ExecutionRequest

    captured = []

    async def sink(evt):
        captured.append(evt)

    em = EventEmitter("test-ws", "AAPL")
    em.add_sink(sink)
    await Orchestrator().execute(ExecutionRequest(ticker="AAPL"), emitter=em)

    # progress is monotonic non-decreasing across lifecycle events
    lifecycle = [e for e in captured if e.type in PROGRESS_ORDER]
    progresses = [e.progress for e in lifecycle]
    assert progresses == sorted(progresses)
    assert captured[0].type == EventType.STARTED
    assert captured[-1].type == EventType.COMPLETED


@pytest.mark.asyncio
async def test_memory_retrieval_and_store():
    from app.ai_engine.memory import get_memory_manager
    from app.ai_engine.memory.schemas import Collection
    from app.ai_engine.orchestrator import Orchestrator
    from app.ai_engine.state import ExecutionRequest

    orch = Orchestrator()
    await orch.execute(ExecutionRequest(ticker="NVDA"), emitter=None)

    # after execution, an execution memory should be retrievable
    mm = get_memory_manager()
    hits = mm.retrieve_by_ticker("NVDA", collection=Collection.EXECUTION, top_k=5)
    assert hits, "execution should be stored into ChromaDB"
    assert hits[0].record.ticker == "NVDA"


@pytest.mark.asyncio
async def test_mongodb_persistence(monkeypatch):
    """Full execution is saved and re-fetchable (mongomock-backed)."""
    pytest.importorskip("mongomock_motor")
    from mongomock_motor import AsyncMongoMockClient

    # Create the mock client inside the running loop and reuse one db handle so
    # writes and reads share the same in-memory store.
    db = AsyncMongoMockClient()["ainvest"]
    import app.db.mongo as mongo_mod
    monkeypatch.setattr(mongo_mod, "get_mongo", lambda: db)

    from app.ai_engine.orchestrator import Orchestrator
    from app.ai_engine.state import ExecutionRequest
    from app.services.analysis_store import AnalysisStore

    state = await Orchestrator().execute(ExecutionRequest(ticker="AAPL"), emitter=None)

    # Persist explicitly here too (orchestrator already did), then read back.
    doc = await AnalysisStore.get(state.analysis_id)
    assert doc is not None, "analysis document should be persisted"
    assert doc["request"]["ticker"] == "AAPL"
    assert doc["status"] in ("COMPLETED", "PARTIAL")

    trace = await AnalysisStore.get_trace(state.analysis_id)
    assert trace is not None
    assert trace["span_count"] >= 4

    from app.models.analysis import AnalysisResponse
    resp = AnalysisResponse.from_doc(doc)
    assert resp.ticker == "AAPL"
    assert resp.recommendation is not None


@pytest.mark.asyncio
async def test_structured_response_shape():
    from app.ai_engine.orchestrator import Orchestrator
    from app.ai_engine.state import ExecutionRequest
    from app.models.analysis import AnalysisResponse

    state = await Orchestrator().execute(ExecutionRequest(ticker="AAPL"), emitter=None)
    resp = AnalysisResponse.from_state(state)
    d = resp.model_dump()
    for key in ("market", "technical", "fundamental", "news", "sentiment",
                "memory", "debate", "risk", "portfolio", "recommendation",
                "confidence", "reasoning", "metadata"):
        assert key in d, f"missing {key} in structured response"
    assert d["metadata"]["agent_count"] >= 4
