# AI Execution Engine (Phase 3)

The orchestration brain. **Every** analysis request in the platform goes through
`Orchestrator.execute()`; routes contain no business logic and never call
TradingAgents/RAEM directly. Built on top of the frozen Phase-2 ChromaDB/RAEM
memory layer, reusing the existing agent pipeline, market-data service, and
WebSocket bus.

## Flow (all inside the Orchestrator)

```
request → validate → fetch market data (Finnhub→Yahoo fallback in service)
        → retrieve RAEM memory (ChromaDB via MemoryManager)
        → run TradingAgents/RAEM pipeline (reused PipelineRunner)
          · Technical / Fundamental / News / Sentiment agents
          · Bull-vs-Bear debate → facilitator
          · Risk debate → risk manager
          · Portfolio manager
        → Chief Investment Officer synthesis → recommendation
        → persist to MongoDB + ChromaDB
        → structured AnalysisResponse
   (ExecutionEvents streamed to WebSocket throughout)
```

The reused `PipelineRunner`'s native events are **translated** into the canonical
event stream and typed state — the agent pipeline itself is unchanged.

## New modules (`app/ai_engine/`)

```
events.py         EventType enum (STARTED…COMPLETED/ERROR) + EventEmitter
state.py          typed Pydantic state: ExecutionState, MarketState, MemoryState,
                  AgentState, DebateState, RiskState, PortfolioState,
                  RecommendationState, ExecutionMetadata  (no raw dicts)
orchestrator.py   Orchestrator — the brain (validate→…→persist), streaming
execution.py      ExecutionService — wires emitter→WebSocket, sync + background
providers/        LLMProvider interface + registry + fallback chain
                  (openai/anthropic/google/deepseek/qwen/mistral/llama/ollama)
tracing/          ExecutionTracer — timed spans persisted to MongoDB
agents/ prompts/ reasoning/ logging/ services/   (package scaffolding)
```

Plus: `models/analysis.py` (the single `AnalysisResponse`),
`services/analysis_store.py` (Mongo persistence), `workers/celery_app.py` +
`workers/tasks.py` (background execution), and the rewritten
`api/routes/analysis.py` (Orchestrator-only, + per-analysis WebSocket).

## Reused unchanged

`ai_engine/memory/*` (MemoryManager/RAEM/ChromaDB), `pipeline/runner.py` &
`pipeline/memory.py` (RAEM engine), `services/market_data.py`, `api/ws.py`
(Redis pub/sub bus), `db/mongo.py`, and all of `tradingagents/`.

## API

```
POST /api/v1/analysis                     run (sync) or {background:true} → ids
GET  /api/v1/analysis/{id}                 full structured AnalysisResponse
GET  /api/v1/analysis/{id}/trace           execution trace (spans/timings)
GET  /api/v1/analysis/{id}/agents          per-agent outputs
GET  /api/v1/analysis/ticker/{t}/history   recent analyses
WS   /ws/analysis/{id}                      live event stream for one execution
WS   /ws                                    global event stream
```

`POST /analysis` body = `ExecutionRequest`:
`{ "ticker": "AAPL", "date": "2026-06-19", "provider": "openai",
   "investment_rounds": 2, "risk_rounds": 3, "background": false }`

## Streaming events

`STARTED · VALIDATING · FETCHING_MARKET_DATA · RETRIEVING_MEMORY ·
RUNNING_TECHNICAL_AGENT · RUNNING_FUNDAMENTAL_AGENT · RUNNING_NEWS_AGENT ·
RUNNING_MACRO_AGENT · RUNNING_SENTIMENT_AGENT · RUNNING_DEBATE ·
RUNNING_RISK_MANAGER · RUNNING_PORTFOLIO_MANAGER · RUNNING_CIO ·
GENERATING_RECOMMENDATION · SAVING_RESULTS · COMPLETED · ERROR`
(plus `AGENT_MESSAGE` for incremental debate/log output). Each carries
`analysis_id`, coarse `progress` (0..1), and payload data; fanned out via Redis
pub/sub to both the global and per-analysis WebSockets.

## Providers & fallback

Selected by `LLM_PROVIDER` in `.env`. `resolve_chain()` orders the primary first,
then every other provider that has credentials; `complete_with_fallback()` tries
each until one succeeds. Market data falls back Finnhub→Yahoo in the service;
a failing agent degrades the run to `PARTIAL` rather than aborting.

## Persistence (MongoDB)

`analyses` — the full ExecutionState (market, agent outputs, reasoning,
confidence, provider, tokens, latency, memory hits, timeline, recommendation,
metadata). `execution_traces` — per-execution spans/timings. Executions are also
written back to ChromaDB (`execution_history`, `agent_reasoning`) via
MemoryManager.

## Background execution

`{"background": true}` dispatches a Celery task (`analysis` queue, Redis broker)
and returns `{analysis_id, task_id, status}`. If no Celery worker/broker is
present, it transparently falls back to an in-process task, so the platform still
works in single-process/dev mode. Clients poll `GET /analysis/{id}` or subscribe
to `WS /ws/analysis/{id}`.

Docker: a `celery_worker` service is added to `docker-compose.yml`, sharing the
Redis broker, Mongo, and the persistent `chromadata` volume.

## Tests

```
cd backend && pytest tests/ -v
```

16 passing (10 Phase-2 memory + 6 Phase-3 engine): complete execution pipeline,
WebSocket event ordering/progress, RAEM retrieval + store, provider fallback,
MongoDB persistence (+trace + structured-response rebuild), and structured
response shape. LLM/network are stubbed so the suite runs offline; a live run
needs your provider key + open network.

*Not investment advice.*
