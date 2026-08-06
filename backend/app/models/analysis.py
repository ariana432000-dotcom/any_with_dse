"""
The single structured response contract for an analysis. Built from the typed
ExecutionState so the API shape is stable and self-documenting.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.ai_engine.state import (
    DebateState,
    ExecutionMetadata,
    ExecutionState,
    MacroState,
    MarketState,
    MemoryState,
    PipelineStep,
    PortfolioState,
    PostMortemState,
    RecommendationState,
    RiskState,
    VerifierState,
)


class AgentView(BaseModel):
    name: str
    signal: str
    confidence: float
    analysis: str
    latency_ms: float
    ok: bool
    error: str | None = None


class AnalysisResponse(BaseModel):
    analysis_id: str
    ticker: str
    status: str
    created_at: str

    market: MarketState | None = None
    technical: AgentView | None = None
    fundamental: AgentView | None = None
    news: AgentView | None = None
    sentiment: AgentView | None = None
    memory: MemoryState | None = None
    debate: DebateState | None = None
    risk: RiskState | None = None
    portfolio: PortfolioState | None = None
    macro: MacroState | None = None
    post_mortem: PostMortemState | None = None
    verifier: VerifierState | None = None
    recommendation: RecommendationState | None = None
    confidence: float = 0.0
    reasoning: str = ""
    metadata: ExecutionMetadata
    pipeline: list[PipelineStep] = []
    error: str | None = None

    @classmethod
    def from_state(cls, s: ExecutionState) -> "AnalysisResponse":
        def view(agent_key: str) -> AgentView | None:
            a = s.agents.get(agent_key)
            if not a:
                return None
            return AgentView(
                name=a.name, signal=a.signal.value, confidence=a.confidence,
                analysis=a.analysis, latency_ms=a.latency_ms, ok=a.ok, error=a.error,
            )

        rec = s.recommendation
        return cls(
            analysis_id=s.analysis_id, ticker=s.ticker, status=s.status.value,
            created_at=s.created_at, market=s.market,
            technical=view("TechnicalAnalyst"),
            fundamental=view("FundamentalAnalyst"),
            news=view("NewsAnalyst"),
            sentiment=view("SentimentAnalyst"),
            memory=s.memory, debate=s.debate, risk=s.risk, portfolio=s.portfolio,
            macro=s.macro, post_mortem=s.post_mortem, verifier=s.verifier,
            recommendation=rec,
            confidence=rec.confidence if rec else 0.0,
            reasoning=rec.reasoning if rec else "",
            metadata=s.metadata, pipeline=s.pipeline, error=s.error,
        )

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "AnalysisResponse":
        """Rebuild from a stored Mongo document."""
        state = ExecutionState.model_validate(doc)
        return cls.from_state(state)
