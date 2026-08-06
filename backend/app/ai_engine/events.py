"""
Execution events — the canonical, ordered set of lifecycle events the engine
emits, plus a typed Event model and an async emitter that fans out to:
  * the WebSocket bus (Redis pub/sub -> connected clients), and
  * an in-memory per-execution buffer (so late subscribers / pollers can replay).

Every stage of the Orchestrator publishes one of these. The frontend switches on
`EventType` to drive its progress UI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field


class EventType(str, Enum):
    STARTED = "STARTED"
    VALIDATING = "VALIDATING"
    FETCHING_MARKET_DATA = "FETCHING_MARKET_DATA"
    RETRIEVING_MEMORY = "RETRIEVING_MEMORY"
    RUNNING_TECHNICAL_AGENT = "RUNNING_TECHNICAL_AGENT"
    RUNNING_FUNDAMENTAL_AGENT = "RUNNING_FUNDAMENTAL_AGENT"
    RUNNING_NEWS_AGENT = "RUNNING_NEWS_AGENT"
    RUNNING_MACRO_AGENT = "RUNNING_MACRO_AGENT"
    RUNNING_SENTIMENT_AGENT = "RUNNING_SENTIMENT_AGENT"
    RUNNING_DEBATE = "RUNNING_DEBATE"
    RUNNING_POST_MORTEM_AGENT = "RUNNING_POST_MORTEM_AGENT"
    RUNNING_RISK_MANAGER = "RUNNING_RISK_MANAGER"
    RUNNING_PORTFOLIO_MANAGER = "RUNNING_PORTFOLIO_MANAGER"
    RUNNING_VERIFIER_AGENT = "RUNNING_VERIFIER_AGENT"
    RUNNING_CIO = "RUNNING_CIO"
    GENERATING_RECOMMENDATION = "GENERATING_RECOMMENDATION"
    SAVING_RESULTS = "SAVING_RESULTS"
    AGENT_MESSAGE = "AGENT_MESSAGE"        # incremental agent output (debate turns, logs)
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class ExecutionEvent(BaseModel):
    analysis_id: str
    type: EventType
    ticker: str = ""
    message: str = ""
    progress: float = 0.0                 # 0..1 coarse progress
    data: dict[str, Any] = Field(default_factory=dict)
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def ws_payload(self) -> dict[str, Any]:
        return {"channel": "analysis", "analysis_id": self.analysis_id,
                "type": self.type.value, "ticker": self.ticker,
                "message": self.message, "progress": self.progress,
                "data": self.data, "ts": self.ts}


# A sink is any async callable that receives an ExecutionEvent.
EventSink = Callable[[ExecutionEvent], Awaitable[None]]


class EventEmitter:
    """Collects events for one execution and fans them out to registered sinks."""

    def __init__(self, analysis_id: str, ticker: str = "") -> None:
        self.analysis_id = analysis_id
        self.ticker = ticker
        self.buffer: list[ExecutionEvent] = []
        self._sinks: list[EventSink] = []

    def add_sink(self, sink: EventSink) -> None:
        self._sinks.append(sink)

    async def emit(self, type_: EventType, message: str = "",
                progress: float = 0.0, **data: Any) -> ExecutionEvent:
        evt = ExecutionEvent(
            analysis_id=self.analysis_id, type=type_, ticker=self.ticker,
            message=message, progress=progress, data=data,
        )
        self.buffer.append(evt)
        for sink in self._sinks:
            try:
                await sink(evt)
            except Exception:  # noqa: BLE001 — a broken sink must not kill execution
                pass
        return evt


# Ordered progress weighting for coarse % (STARTED..COMPLETED).
PROGRESS_ORDER: list[EventType] = [
    EventType.STARTED, EventType.VALIDATING, EventType.FETCHING_MARKET_DATA,
    EventType.RETRIEVING_MEMORY, EventType.RUNNING_TECHNICAL_AGENT,
    EventType.RUNNING_FUNDAMENTAL_AGENT, EventType.RUNNING_NEWS_AGENT,
    EventType.RUNNING_MACRO_AGENT, EventType.RUNNING_SENTIMENT_AGENT,
    EventType.RUNNING_DEBATE, EventType.RUNNING_POST_MORTEM_AGENT,
    EventType.RUNNING_RISK_MANAGER, EventType.RUNNING_PORTFOLIO_MANAGER,
    EventType.RUNNING_VERIFIER_AGENT, EventType.RUNNING_CIO,
    EventType.GENERATING_RECOMMENDATION, EventType.SAVING_RESULTS,
    EventType.COMPLETED,
]


def progress_for(event_type: EventType) -> float:
    try:
        return round(PROGRESS_ORDER.index(event_type) / (len(PROGRESS_ORDER) - 1), 3)
    except ValueError:
        return 0.0
