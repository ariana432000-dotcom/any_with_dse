"""
Orchestrator — the brain. Every analysis request in the platform goes through
`Orchestrator.execute()`. Routes never call TradingAgents/RAEM directly.

Responsibilities (all here, none in routes):
  validate -> fetch market data -> retrieve RAEM memory -> run the
  TradingAgents/RAEM pipeline (reused PipelineRunner, the same agent graph,
  prompts, debate, and tool-calling as the notebook) mapping its events to the
  canonical stream (technical/fundamental/news/sentiment agents, debate, risk,
  portfolio) -> synthesize a recommendation from the Portfolio Manager's
  decision (pure Python, no extra LLM call) -> persist to Mongo + ChromaDB
  (via MemoryManager) -> return a typed ExecutionState. Emits ExecutionEvents
  throughout for WebSocket streaming.

TradingAgents (via the reused PipelineRunner/pipeline.llm factory) is the only
AI engine here — this module makes no LLM calls of its own.

Reuses (unchanged): services.market_data, ai_engine.memory (MemoryManager/RAEM),
pipeline.runner.PipelineRunner, db.mongo.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

from app.ai_engine.events import EventEmitter, EventType, progress_for
from app.ai_engine.memory import MemoryManager, get_memory_manager
from app.ai_engine.memory.schemas import Collection, MemoryRecord
from app.ai_engine.state import (
    AgentState,
    DebateState,
    DebateTurn,
    ExecutionMetadata,
    ExecutionRequest,
    ExecutionState,
    ExecutionStatus,
    MacroState,
    MarketState,
    MemoryHit,
    MemoryState,
    PipelineStep,
    PortfolioState,
    PostMortemState,
    RecommendationState,
    RiskState,
    Signal,
    VerifierState,
)
from app.ai_engine.tracing import ExecutionTracer
from app.core.logging import get_logger
from app.services import market_data as mds
from app.services.analysis_store import AnalysisStore

log = get_logger(__name__)

# Map the reused PipelineRunner stage ids -> canonical events + typed agent names.
_STAGE_TO_EVENT = {
    "market": (EventType.RUNNING_TECHNICAL_AGENT, "TechnicalAnalyst"),
    "fundamentals": (EventType.RUNNING_FUNDAMENTAL_AGENT, "FundamentalAnalyst"),
    "news": (EventType.RUNNING_NEWS_AGENT, "NewsAnalyst"),
    "sentiment": (EventType.RUNNING_SENTIMENT_AGENT, "SentimentAnalyst"),
    "macro_regime": (EventType.RUNNING_MACRO_AGENT, "MacroRegimeAnalyst"),
    "investment_debate": (EventType.RUNNING_DEBATE, "DebateAgent"),
    "investment_facilitator": (EventType.RUNNING_DEBATE, "DebateFacilitator"),
    "memory": (EventType.RETRIEVING_MEMORY, "MemoryAgent"),
    "post_mortem": (EventType.RUNNING_POST_MORTEM_AGENT, "PostMortemAgent"),
    "trader": (EventType.RUNNING_PORTFOLIO_MANAGER, "Trader"),
    "risk_debate": (EventType.RUNNING_RISK_MANAGER, "RiskManager"),
    "risk_facilitator": (EventType.RUNNING_RISK_MANAGER, "RiskFacilitator"),
    "portfolio_manager": (EventType.RUNNING_PORTFOLIO_MANAGER, "PortfolioManager"),
    "decision_verifier": (EventType.RUNNING_VERIFIER_AGENT, "DecisionVerifier"),
}

_SIGNAL_RE = re.compile(r"\*{0,2}(BUY|HOLD|SELL)\*{0,2}", re.IGNORECASE)


def _signal(text: str) -> Signal:
    m = _SIGNAL_RE.search(text or "")
    return Signal(m.group(1).upper()) if m else Signal.NA


class Orchestrator:
    def __init__(self, memory: MemoryManager | None = None) -> None:
        self.memory = memory or get_memory_manager()

    # ------------------------------------------------------------------ run
    async def execute(self, request: ExecutionRequest,
                    emitter: EventEmitter | None = None) -> ExecutionState:
        state = ExecutionState(request=request, status=ExecutionStatus.RUNNING)
        emitter = emitter or EventEmitter(state.analysis_id, state.ticker)
        # If the caller pre-created an emitter with an id, adopt it so the
        # streamed events and the stored record share one analysis_id.
        if emitter.analysis_id:
            state.analysis_id = emitter.analysis_id
        else:
            emitter.analysis_id = state.analysis_id
        emitter.ticker = state.ticker
        tracer = ExecutionTracer(state.analysis_id, state.ticker)
        state.metadata.started_at = datetime.now(timezone.utc).isoformat()
        t_start = datetime.now(timezone.utc)

        await emitter.emit(EventType.STARTED, f"Analysis started for {state.ticker}",
                        progress_for(EventType.STARTED), analysis_id=state.analysis_id)
        await AnalysisStore.set_status(state.analysis_id, ExecutionStatus.RUNNING)

        try:
            # 1. validate
            await emitter.emit(EventType.VALIDATING, "Validating request",
                            progress_for(EventType.VALIDATING))
            with tracer.span("validate"):
                self._validate(request)

            # 2. market data (Finnhub -> Yahoo fallback lives in the service)
            await emitter.emit(EventType.FETCHING_MARKET_DATA, "Fetching live market data",
                            progress_for(EventType.FETCHING_MARKET_DATA))
            with tracer.span("market_data"):
                state.market = await self._fetch_market(state)

            # 3. RAEM memory retrieval
            await emitter.emit(EventType.RETRIEVING_MEMORY, "Retrieving RAEM memory",
                            progress_for(EventType.RETRIEVING_MEMORY))
            with tracer.span("memory_retrieval"):
                state.memory = await self._retrieve_memory(state)
            await emitter.emit(EventType.RETRIEVING_MEMORY,
                            f"{state.memory.episodic_count} prior episodes",
                            progress_for(EventType.RETRIEVING_MEMORY),
                            hits=len(state.memory.hits), regime=state.memory.regime)

            # 4-12. run the reused TradingAgents/RAEM pipeline, streaming events
            with tracer.span("agent_pipeline"):
                await self._run_pipeline(state, emitter, tracer)

            # 13. recommendation synthesis — pure Python roll-up of the
            # Portfolio Manager's decision + agent outputs, no extra LLM call.
            await emitter.emit(EventType.RUNNING_CIO, "Finalizing recommendation",
                            progress_for(EventType.RUNNING_CIO))
            await emitter.emit(EventType.GENERATING_RECOMMENDATION, "Generating recommendation",
                            progress_for(EventType.GENERATING_RECOMMENDATION))
            with tracer.span("recommendation"):
                state.recommendation = self._synthesize(state)

            # 14. persist (Mongo + Chroma)
            await emitter.emit(EventType.SAVING_RESULTS, "Saving results",
                            progress_for(EventType.SAVING_RESULTS))
            if state.error:
                # Top-level pipeline crash (see the "error"/stage=="pipeline"
                # handling in _run_pipeline) — nothing usable ran.
                state.status = ExecutionStatus.FAILED
            else:
                state.status = (ExecutionStatus.PARTIAL
                                if state.metadata.failed_agents else ExecutionStatus.COMPLETED)
            self._finalize_metadata(state, emitter, t_start)
            with tracer.span("persist"):
                await AnalysisStore.save(state)
                await asyncio.to_thread(self._store_memory, state)

            await tracer.persist()
            await emitter.emit(EventType.COMPLETED,
                            f"{state.recommendation.signal.value} · "
                            f"confidence {state.recommendation.confidence:.0%}",
                            1.0, signal=state.recommendation.signal.value,
                            confidence=state.recommendation.confidence)
            return state

        except Exception as e:  # noqa: BLE001
            state.status = ExecutionStatus.FAILED
            state.error = str(e)
            self._finalize_metadata(state, emitter, t_start)
            log.exception("execution failed id=%s: %s", state.analysis_id, e)
            with_suppress = True
            try:
                await AnalysisStore.save(state)
                await tracer.persist()
            except Exception:  # noqa: BLE001
                with_suppress = False
            await emitter.emit(EventType.ERROR, f"Execution failed: {e}", 1.0, error=str(e))
            return state

    # ------------------------------------------------------------- stages
    @staticmethod
    def _validate(request: ExecutionRequest) -> None:
        if not request.ticker or not request.ticker.strip():
            raise ValueError("ticker is required")
        if not re.fullmatch(r"[A-Za-z0-9.\-]{1,12}", request.ticker.strip()):
            raise ValueError(f"invalid ticker: {request.ticker!r}")

    async def _fetch_market(self, state: ExecutionState) -> MarketState:
        ticker = state.ticker
        try:
            hist = await mds.get_history(ticker, days_back=220, asset_type=state.request.asset_type)
            quote = await mds.get_quote(ticker)
            news = await mds.get_news(ticker, limit=6)
            ms = MarketState(
                ticker=ticker, provider=hist.get("provider", ""),
                latest_close=hist.get("latest_close"),
                change_pct=quote.get("change_pct"),
                indicators=hist.get("indicators", {}),
                rows=hist.get("rows", [])[-60:],  # trim payload
                news=news, fetched_at=hist.get("fetched_at", ""),
                ok=bool(hist.get("rows")),
            )
            if not ms.ok:
                ms.error = "no market rows returned (provider/network)"
            return ms
        except Exception as e:  # noqa: BLE001
            log.warning("market fetch failed for %s: %s", ticker, e)
            return MarketState(ticker=ticker, ok=False, error=str(e))

    async def _retrieve_memory(self, state: ExecutionState) -> MemoryState:
        ticker = state.ticker
        indicators = state.market.indicators if state.market else {}
        # regime tag reuses RAEM's classifier (unchanged)
        from app.pipeline.memory import classify_regime
        regime = classify_regime(indicators) if indicators else ""

        try:
            hits_raw = await asyncio.to_thread(
                self.memory.retrieve_similar,
                f"Trading decision for {ticker} in {regime} regime",
                Collection.EPISODIC, 5, None, ticker=ticker,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("memory retrieval failed: %s", e)
            hits_raw = []

        hits = [
            MemoryHit(
                memory_id=h.record.memory_id, ticker=h.record.ticker,
                timestamp=h.record.timestamp, market_regime=h.record.market_regime,
                decision=h.record.decision, outcome=h.record.outcome,
                similarity=h.similarity,
            ) for h in hits_raw
        ]
        context = self._format_context(regime, hits)
        return MemoryState(regime=regime, hits=hits, injected_context=context,
                        episodic_count=len(hits))

    @staticmethod
    def _format_context(regime: str, hits: list[MemoryHit]) -> str:
        if not hits:
            return f"No prior episodes for this ticker in {regime or 'this'} regime."
        lines = [f"Past episodes in {regime} regime:"]
        for h in hits:
            lines.append(
                f"- {h.timestamp[:10]} {h.decision} · outcome={h.outcome} "
                f"· sim={h.similarity:.2f}" if h.similarity is not None
                else f"- {h.timestamp[:10]} {h.decision} · outcome={h.outcome}"
            )
        return "\n".join(lines)

    async def _run_pipeline(self, state: ExecutionState, emitter: EventEmitter,
                            tracer: ExecutionTracer) -> None:
        """Run the reused PipelineRunner, translating its events into the
        canonical stream + typed AgentStates. The pipeline itself is unchanged."""
        from app.pipeline.runner import PipelineRunner

        runner = PipelineRunner(
            state.ticker, state.request.date or datetime.now().strftime("%Y-%m-%d"),
            state.request.asset_type,
            investment_rounds=state.request.investment_rounds,
            risk_rounds=state.request.risk_rounds,
        )

        # The runner is a sync generator; iterate it off-thread, forwarding each
        # event to an asyncio.Queue consumed here so we can emit + build state.
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _produce():
            try:
                for ev in runner.run():
                    loop.call_soon_threadsafe(queue.put_nowait, ev)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, {"type": "__end__"})

        producer = asyncio.create_task(asyncio.to_thread(_produce))
        stage_started: dict[str, float] = {}
        stage_started_iso: dict[str, str] = {}
        stage_label: dict[str, str] = {}

        while True:
            ev = await queue.get()
            etype = ev.get("type")
            if etype == "__end__":
                break

            if etype == "stage_start":
                stage = ev.get("stage", "")
                stage_started[stage] = loop.time()
                stage_started_iso[stage] = datetime.now(timezone.utc).isoformat()
                stage_label[stage] = ev.get("label", stage)
                mapped = _STAGE_TO_EVENT.get(stage)
                if mapped:
                    canon, agent = mapped
                    await emitter.emit(canon, f"{agent} running", progress_for(canon),
                                    stage=stage, agent=agent)

            elif etype == "regime":
                if state.memory:
                    state.memory.regime = ev.get("regime", state.memory.regime)

            elif etype == "debate_turn":
                if state.debate is None:
                    state.debate = DebateState()
                state.debate.turns.append(DebateTurn(
                    speaker=ev.get("speaker", ""), side=ev.get("side", ""),
                    round=ev.get("round", 0),
                    content=_strip_html(ev.get("html", ""))[:1200],
                ))
                await emitter.emit(EventType.AGENT_MESSAGE, ev.get("speaker", "debate"),
                                data_side=ev.get("side"), round=ev.get("round"))

            elif etype == "stage_done":
                stage = ev.get("stage", "")
                mapped = _STAGE_TO_EVENT.get(stage)
                latency = (loop.time() - stage_started.get(stage, loop.time())) * 1000
                html = ev.get("html", "")
                meta = ev.get("meta") or {}
                if mapped:
                    _canon, agent = mapped
                    self._record_agent(state, agent, html, meta, latency)
                self._absorb_stage(state, stage, html, meta)
                self._record_pipeline_step(
                    state, stage, stage_label.get(stage, stage),
                    ev.get("input") or {}, html, meta,
                    stage_started_iso.get(stage, ""), latency,
                )

            elif etype == "final":
                # captured in _synthesize via portfolio_manager stage_done + this
                if state.portfolio is None:
                    state.portfolio = PortfolioState()
                state.portfolio.signal = _signal(ev.get("signal", ""))

            elif etype == "error":
                msg = ev.get("message", "pipeline error")
                # Log the full message (incl. traceback) server-side — the
                # streamed event below is truncated and not persisted, so
                # without this the only record of a pipeline crash is lost
                # once the WebSocket disconnects.
                log.error("pipeline error id=%s stage=%s: %s",
                          state.analysis_id, ev.get("stage", "pipeline"), msg)
                if ev.get("stage") == "pipeline":
                    # A top-level crash before/between stages — nothing ran,
                    # so surface it as a real failure instead of silently
                    # completing with empty agent cards.
                    state.error = msg.splitlines()[0][:500] if msg else "pipeline error"
                await emitter.emit(EventType.AGENT_MESSAGE, f"stage error: {msg[:200]}")

        await producer

    # -------------------------------------------------------- state builders
    def _record_agent(self, state: ExecutionState, agent: str, html: str,
                    meta: dict, latency_ms: float) -> None:
        text = _strip_html(html)
        conf = float(meta.get("confidence", 0.0) or 0.0)
        ok = True
        err = None
        if "error" in (meta or {}) or (not text and not meta):
            ok = False
            err = str(meta.get("error", "no output"))
            if agent not in state.metadata.failed_agents:
                state.metadata.failed_agents.append(agent)
        state.agents[agent] = AgentState(
            name=agent, analysis=text[:6000], confidence=conf,
            reasoning=text[:2000], signal=_signal(text),
            metadata=meta if isinstance(meta, dict) else {},
            latency_ms=round(latency_ms, 1), ok=ok, error=err,
        )

    def _record_pipeline_step(self, state: ExecutionState, stage: str, label: str,
                            step_input: dict, html: str, meta: dict,
                            started_at: str, latency_ms: float) -> None:
        """Append one PipelineStep — powers the analysis page's agent flow
        view (click a node -> see exactly what it fetched / returned)."""
        text = _strip_html(html)
        output: dict = dict(meta) if isinstance(meta, dict) else {}

        # investment_debate / risk_debate stage_done events carry no html of
        # their own (the content streamed earlier as per-turn debate_turn
        # events) — pull the accumulated turns back out of state.debate so
        # the flow view still shows real argument text, not an empty output.
        if stage == "investment_debate" and state.debate:
            sides = {"bull", "bear"}
            turns = [t for t in state.debate.turns if t.side in sides]
            if turns:
                output["transcript"] = "\n\n".join(f"{t.speaker}: {t.content}" for t in turns)[:4000]
        elif stage == "risk_debate" and state.debate:
            sides = {"aggressive", "conservative", "neutral"}
            turns = [t for t in state.debate.turns if t.side in sides]
            if turns:
                output["transcript"] = "\n\n".join(f"{t.speaker}: {t.content}" for t in turns)[:4000]
        elif text:
            output["summary"] = text[:3000]

        state.pipeline.append(PipelineStep(
            stage=stage, label=label,
            input=step_input if isinstance(step_input, (dict, str)) else {},
            output=output,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            latency_ms=round(latency_ms, 1),
        ))

    def _absorb_stage(self, state: ExecutionState, stage: str, html: str, meta: dict) -> None:
        text = _strip_html(html)
        if stage == "risk_facilitator":
            state.risk = RiskState(
                rating=_extract(text, r"(LOW|MEDIUM|HIGH)\s*(?:risk)?", "MEDIUM"),
                position_sizing=_extract(text, r"(\d{1,3}\s*%)", ""),
                stop_loss=_extract_price(text, r"stop[- ]?loss"),
                take_profit=_extract_price(text, r"take[- ]?profit"),
                summary=text[:800],
            )
        elif stage == "portfolio_manager":
            sig = _signal(text)
            if state.portfolio is None:
                state.portfolio = PortfolioState()
            state.portfolio.signal = sig
            state.portfolio.rationale = text[:800]
            # keep the PM narrative for the recommendation synthesis
            state.metadata.__dict__.setdefault("_pm_text", text)
            self._pm_text = text
        elif stage == "memory" and state.memory is not None:
            state.memory.injected_context = text[:1500] or state.memory.injected_context
        elif stage == "macro_regime":
            snap = meta.get("macro_snapshot") or {}

            def _f(key, sub):
                try:
                    return float((snap.get(key) or {}).get(sub))
                except (TypeError, ValueError):
                    return None

            state.macro = MacroState(
                regime=meta.get("macro_regime", ""), report=text[:2000],
                vix=_f("vix", "latest"), vix_avg=_f("vix", "avg"),
                tnx=_f("tnx", "latest"), tnx_avg=_f("tnx", "avg"),
                dxy=_f("dxy", "latest"), dxy_avg=_f("dxy", "avg"),
            )
        elif stage == "post_mortem":
            state.post_mortem = PostMortemState(
                lessons=text[:3000], episodes_reviewed=int(meta.get("episodes_reviewed", 0) or 0),
            )
        elif stage == "decision_verifier":
            state.verifier = VerifierState(
                status=meta.get("status", ""), notes=meta.get("notes", "")[:3000],
                raw_signal=_signal(meta.get("final_signal", "")),
                effective_signal=_signal(meta.get("effective_signal", "")),
                auto_overridden=bool(meta.get("auto_overridden", False)),
            )
            # The verifier runs AFTER portfolio_manager, so state.portfolio.signal
            # above is still the raw, pre-verification call. On an auto-override
            # (raw signal directly contradicts the Fundamentals Analyst's own
            # verdict) that raw signal is no longer the actionable one — without
            # this, the Risk & Portfolio panel would keep showing e.g. "BUY" even
            # though the effective/actionable signal is HOLD.
            if state.verifier.auto_overridden and state.verifier.effective_signal != Signal.NA:
                if state.portfolio is None:
                    state.portfolio = PortfolioState()
                raw = state.portfolio.signal
                state.portfolio.signal = state.verifier.effective_signal
                note = (f"\n\n[Auto-overridden by Decision Verifier: raw call was {raw.value}, "
                        f"downgraded to {state.verifier.effective_signal.value} — it directly "
                        f"contradicted the Fundamentals Analyst's own verdict.]")
                if note not in state.portfolio.rationale:
                    state.portfolio.rationale = (state.portfolio.rationale or "")[:800] + note

    def _synthesize(self, state: ExecutionState) -> RecommendationState:
        """Roll up the Portfolio Manager's decision + agent outputs into one
        recommendation. Pure Python — no LLM call; the actual decision was
        already made by TradingAgents' portfolio_manager stage."""
        pm_text = getattr(self, "_pm_text", "") or (
            state.portfolio.rationale if state.portfolio else "")
        signal = state.portfolio.signal if state.portfolio and state.portfolio.signal != Signal.NA \
            else _signal(pm_text)

        # The Decision Verifier can auto-downgrade to HOLD when the final call
        # directly contradicts the Fundamentals Analyst's own verdict — that
        # effective/actionable signal takes priority over the raw PM signal.
        override_note = ""
        if state.verifier and state.verifier.auto_overridden and state.verifier.effective_signal != Signal.NA:
            signal = state.verifier.effective_signal
            override_note = " · verifier auto-overrode to HOLD"

        # confidence = mean of agent confidences that reported one, else derived
        confs = [a.confidence for a in state.agents.values() if a.confidence > 0]
        confidence = round(sum(confs) / len(confs), 3) if confs else _confidence_from_agreement(state)

        entry = state.market.latest_close if state.market else None
        risk = state.risk or RiskState()
        rec = RecommendationState(
            signal=signal, confidence=confidence, entry_price=entry,
            stop_loss=risk.stop_loss, take_profit=risk.take_profit,
            time_horizon="1-4 weeks",
            bull_case=_side_case(state, "bull"),
            bear_case=_side_case(state, "bear"),
            reasoning=pm_text[:2000] or "Synthesized from analyst consensus.",
            summary=f"{signal.value} {state.ticker} · confidence {confidence:.0%} "
                    f"· regime {state.memory.regime if state.memory else 'N/A'}{override_note}",
        )
        return rec

    def _finalize_metadata(self, state: ExecutionState, emitter: EventEmitter,
                        t_start: datetime) -> None:
        md = state.metadata
        md.finished_at = datetime.now(timezone.utc).isoformat()
        md.total_latency_ms = round((datetime.now(timezone.utc) - t_start).total_seconds() * 1000, 1)
        md.agent_count = len(state.agents)
        md.memory_hits = state.memory.episodic_count if state.memory else 0
        md.event_count = len(emitter.buffer)
        md.tokens = sum(a.tokens for a in state.agents.values())
        md.provider = state.request.provider or ""

    def _store_memory(self, state: ExecutionState) -> None:
        """Persist the execution back into ChromaDB via MemoryManager."""
        rec = state.recommendation or RecommendationState()
        record = MemoryRecord(
            ticker=state.ticker,
            market_regime=state.memory.regime if state.memory else "",
            agent_name="ChiefInvestmentOfficer",
            summary=rec.summary, reasoning=rec.reasoning,
            decision=rec.signal.value, confidence=rec.confidence,
            source="orchestrator", outcome="PENDING",
            tags=[state.ticker, rec.signal.value],
            metadata={"analysis_id": state.analysis_id,
                    "date": state.request.date or ""},
        )
        try:
            self.memory.store_memory(Collection.EXECUTION, record)
            for name, agent in state.agents.items():
                self.memory.store_memory(Collection.AGENT_REASONING, MemoryRecord(
                    ticker=state.ticker, agent_name=name,
                    market_regime=record.market_regime, summary=f"{name} · {state.ticker}",
                    reasoning=agent.reasoning[:3000], decision=agent.signal.value,
                    confidence=agent.confidence, source="orchestrator",
                    metadata={"analysis_id": state.analysis_id},
                ))
        except Exception as e:  # noqa: BLE001
            log.warning("chroma store failed id=%s: %s", state.analysis_id, e)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _strip_html(html: str) -> str:
    if not html:
        return ""
    return re.sub(r"<[^>]+>", " ", html).replace("&amp;", "&").replace("&nbsp;", " ").strip()


def _extract(text: str, pattern: str, default: str = "") -> str:
    m = re.search(pattern, text or "", re.IGNORECASE)
    return m.group(1).upper() if m else default


def _extract_price(text: str, label_pattern: str) -> float | None:
    """🔴 FIXED: RiskState's stop_loss/take_profit were never populated at
    all -- _absorb_stage only ever set rating/position_sizing/summary from
    the risk facilitator's text, so these fields stayed None forever
    (shown as "—" in the Recommendation panel) even though the risk
    facilitator's own prompt explicitly asks it to "Set stop-loss and
    take-profit levels". This finds a price-like number near a label
    ("stop-loss", "take-profit") in that free-form text, tolerating
    connectors ("at", "around", "of"), a $/Tk currency prefix, and commas
    in the number -- same style as _extract_cited_number in agents.py's
    decision verifier."""
    m = re.search(
        rf"{label_pattern}\b[^0-9\-]{{0,25}}[\$৳]?\s*(?:Tk\.?\s*)?(-?[\d,]+\.?\d*)",
        text or "", re.IGNORECASE,
    )
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _side_case(state: ExecutionState, side: str) -> str:
    if not state.debate:
        return ""
    turns = [t.content for t in state.debate.turns if t.side == side]
    return turns[-1][:600] if turns else ""


def _confidence_from_agreement(state: ExecutionState) -> float:
    signals = [a.signal for a in state.agents.values() if a.signal != Signal.NA]
    if not signals:
        return 0.5
    top = max(set(signals), key=signals.count)
    return round(signals.count(top) / len(signals), 3)


# shared singleton
_orch: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orch
    if _orch is None:
        _orch = Orchestrator()
    return _orch
