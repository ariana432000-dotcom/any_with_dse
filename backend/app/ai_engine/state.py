"""
Strongly-typed execution state — no raw dicts flow through the engine.

The Orchestrator threads a single `ExecutionState` through each stage; every
stage fills in its typed sub-state (market, memory, per-agent, portfolio,
recommendation). These models are also what get serialized into MongoDB and the
final AnalysisResponse, so they are the single source of truth for shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _uid() -> str:
    return uuid.uuid4().hex


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NA = "N/A"


class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"       # finished but one or more agents failed


# --------------------------------------------------------------------------
class MarketState(BaseModel):
    ticker: str
    provider: str = ""
    latest_close: float | None = None
    change_pct: float | None = None
    indicators: dict[str, Any] = Field(default_factory=dict)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    news: list[dict[str, Any]] = Field(default_factory=list)
    fetched_at: str = ""
    ok: bool = False
    error: str | None = None


class MemoryHit(BaseModel):
    memory_id: str = ""
    ticker: str = ""
    timestamp: str = ""
    market_regime: str = ""
    decision: str = ""
    outcome: str = ""
    similarity: float | None = None


class MemoryState(BaseModel):
    regime: str = ""
    hits: list[MemoryHit] = Field(default_factory=list)
    injected_context: str = ""
    episodic_count: int = 0


class AgentState(BaseModel):
    name: str
    analysis: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    signal: Signal = Signal.NA
    metadata: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    provider: str = ""
    tokens: int = 0
    ok: bool = True
    error: str | None = None


class DebateTurn(BaseModel):
    speaker: str
    side: str = ""          # bull/bear/aggressive/conservative/neutral
    round: int = 0
    content: str = ""


class DebateState(BaseModel):
    turns: list[DebateTurn] = Field(default_factory=list)
    winner: str = ""
    summary: str = ""


class RiskState(BaseModel):
    rating: str = ""        # LOW/MEDIUM/HIGH
    position_sizing: str = ""
    stop_loss: float | None = None
    take_profit: float | None = None
    summary: str = ""


class PortfolioState(BaseModel):
    signal: Signal = Signal.NA
    allocation_pct: float | None = None
    rationale: str = ""


class MacroState(BaseModel):
    """Market-wide risk regime (VIX / 10Y yield / DXY) — independent of the
    stock-specific technical regime in MemoryState.regime."""
    regime: str = ""       # RISK_OFF_HIGH_VOL / RISK_ON_LOW_VOL / RATES_RISING / RATES_FALLING / NEUTRAL_MACRO
    report: str = ""
    vix: float | None = None
    vix_avg: float | None = None
    tnx: float | None = None
    tnx_avg: float | None = None
    dxy: float | None = None
    dxy_avg: float | None = None
    # DSE tickers use the DSEX broad index + its realized volatility instead
    # of VIX/10Y/DXY (see fetch_dse_macro_snapshot) -- populated instead of
    # the fields above when that path fires, left None otherwise.
    dsex: float | None = None
    dsex_avg: float | None = None
    dsex_volatility_pct: float | None = None


class PostMortemState(BaseModel):
    """Cross-regime self-critique over a ticker's full RESOLVED track record,
    run every session (unlike the regime-transition reflection, which only
    fires on a regime change and only looks at the prior regime)."""
    lessons: str = ""
    episodes_reviewed: int = 0


class VerifierState(BaseModel):
    """Post-decision sanity check: rule-based + deterministic-numeric +
    advisory-LLM checks on the Portfolio Manager's final call. Can
    auto-downgrade the actionable signal to HOLD on a hard contradiction."""
    status: str = ""        # VERIFIED / FLAGGED
    notes: str = ""
    raw_signal: Signal = Signal.NA
    effective_signal: Signal = Signal.NA
    auto_overridden: bool = False


class RecommendationState(BaseModel):
    signal: Signal = Signal.NA
    confidence: float = 0.0
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    time_horizon: str = ""
    bull_case: str = ""
    bear_case: str = ""
    reasoning: str = ""
    summary: str = ""
    # 🔴 FIXED: entry_price/stop_loss/take_profit were always rendered with
    # a hardcoded "$" (USD) prefix on the frontend (formatCurrency's
    # currency: "USD" was never conditional) -- for a DSE ticker these are
    # real BDT amounts, so a value like 241.00 displayed as "$241.00"
    # rather than the correct "৳241.00", misrepresenting the number by
    # ~120x if read as USD. Added so the frontend can format correctly.
    currency: str = "USD"


class PipelineStep(BaseModel):
    """One node in the agent pipeline flow — what a single stage received as
    input and produced as output. Powers the analysis page's pipeline flow
    view (click an agent -> see exactly what it fetched / returned)."""
    stage: str                              # matches app/pipeline/runner.py STAGES ids
    label: str = ""
    input: dict[str, Any] | str = Field(default_factory=dict)
    output: dict[str, Any] | str = Field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""
    latency_ms: float = 0.0


class ExecutionMetadata(BaseModel):
    provider: str = ""
    total_latency_ms: float = 0.0
    agent_count: int = 0
    failed_agents: list[str] = Field(default_factory=list)
    memory_hits: int = 0
    event_count: int = 0
    tokens: int = 0
    started_at: str = ""
    finished_at: str = ""


class ExecutionRequest(BaseModel):
    ticker: str
    date: str | None = None
    asset_type: str = "stock"
    provider: str | None = None       # override .env provider for this run
    investment_rounds: int | None = None
    risk_rounds: int | None = None
    background: bool = False


class ExecutionState(BaseModel):
    analysis_id: str = Field(default_factory=_uid)
    task_id: str | None = None
    request: ExecutionRequest
    status: ExecutionStatus = ExecutionStatus.PENDING
    created_at: str = Field(default_factory=_now)

    market: MarketState | None = None
    memory: MemoryState | None = None
    agents: dict[str, AgentState] = Field(default_factory=dict)
    debate: DebateState | None = None
    risk: RiskState | None = None
    portfolio: PortfolioState | None = None
    macro: MacroState | None = None
    post_mortem: PostMortemState | None = None
    verifier: VerifierState | None = None
    recommendation: RecommendationState | None = None
    metadata: ExecutionMetadata = Field(default_factory=ExecutionMetadata)
    pipeline: list[PipelineStep] = Field(default_factory=list)
    error: str | None = None

    @property
    def ticker(self) -> str:
        return self.request.ticker.upper()
