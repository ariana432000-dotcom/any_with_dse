# AInvest Platform

An AI trading research platform. FastAPI backend, **TradingAgents** as the
single AI engine (Claude Sonnet 5 by default via the Anthropic API — a local,
keyless Ollama mode is also available if you'd rather not use a cloud key),
the notebook's **RAEM ChromaDB episodic memory**, MongoDB, a live WebSocket
event stream, and a Next.js 15 dashboard. Single local user — no login, no
accounts.

---

## Quick start

```bash
cp .env.example .env          # then set ANTHROPIC_API_KEY in .env
docker compose up --build     # mongo, redis, api, worker, celery_worker, web
```

Prefer to run fully local/keyless instead? In `.env`, set
`RAEM_LLM_PROVIDER=ollama` and make sure Ollama is running on your host with
the model pulled (`ollama pull qwen2.5`) before `docker compose up`.

- Dashboard: http://localhost:3000
- API: http://localhost:8000  ·  Docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health

Backend only, without Docker:

```bash
cd backend
pip install -r requirements.txt
# point Mongo/Redis at local instances or run the docker DBs; then:
python run.py                 # http://localhost:8000
```

Frontend only, without Docker:

```bash
cd frontend
npm install
npm run dev                   # http://localhost:3000
```

---

## What's here

| Area | Status |
|---|---|
| FastAPI app + OpenAPI docs + CORS + WebSocket hub | working |
| No auth — every route open, single local user | working |
| MongoDB (Motor) — analyses/market/news/conversations collections + indexes | working |
| Redis — WebSocket pub/sub fan-out + optional Celery broker | working |
| ChromaDB RAEM episodic memory (from the notebook), local + persistent | working |
| TradingAgents — the only AI engine (agent graph, prompts, debate, tool-calling reused as-is) | working |
| Claude Sonnet 5 by default (`RAEM_LLM_PROVIDER=anthropic`) — local/keyless Ollama also supported | working |
| Market data — live quote/history/indicators/news (Yahoo/Stooq, keyless) | working |
| `/api/v1/analysis` — run the full pipeline (sync or background), poll, stream via WebSocket | working |
| `/api/v1/memory` — inspect/search the ChromaDB memory layer | working |
| Background worker — watchlist refresh + WebSocket heartbeat | working |
| Celery worker — optional; background analysis runs fall back in-process without it | working |
| Frontend — Next.js 15 dashboard (`./frontend`): analysis, AI debate, memory viewer, watchlist, news, settings, live progress via WebSocket | working |

Frontend quick start: `cd frontend && npm install && npm run dev` → http://localhost:3000
(no `.env` needed — it defaults to this backend at `http://localhost:8000`;
see `frontend/README.md` for details).

---

## Configuration

Everything is env-driven — see `.env.example`. Highlights:

- **AI provider** (`RAEM_LLM_PROVIDER`, in `backend/app/pipeline/llm.py` —
  the single source of truth for LLM access in this app): `anthropic`
  (default — needs `ANTHROPIC_API_KEY`, model via `RAEM_LLM_MODEL`, e.g.
  `claude-sonnet-5`) / `ollama` (local, no key — pull a model first with
  `ollama pull <model>`, e.g. `qwen2.5:7b`, `llama3.1`, `mistral`, `phi4`,
  `deepseek-r1`) / `openai` / `groq`.
  (Note: the vendored `tradingagents/llm_clients` factory separately
  supports a wider set of providers — google/deepseek/mistral/qwen/
  openrouter/azure/bedrock/etc. — but that factory isn't what this app's
  running pipeline calls; `RAEM_LLM_PROVIDER` above is what actually takes
  effect.)
- **Market data**: Yahoo/Stooq work with no key, via TradingAgents'
  dataflows and the ported pipeline helpers. Finnhub/Polygon/AlphaVantage/
  TwelveData/FMP/FRED/NewsAPI activate when their key is set.
- **Databases**: default hostnames match the compose service names.

---

## Architecture

```
backend/
  app/
    main.py            FastAPI app + lifespan + WebSocket (no auth)
    core/               config, logging
    db/                 mongo, redis
    models/              analysis.py, schemas.py (Health only)
    api/routes/           health, stocks, memory, analysis
    ai_engine/
      orchestrator.py     validate -> market data -> RAEM memory ->
                          run PipelineRunner (reused) -> roll up recommendation
                          (pure Python, no extra LLM call) -> persist
      execution.py         wires the orchestrator to WebSocket + Celery/in-process
      events.py, state.py, tracing/    typed event stream + execution state
      memory/              MemoryManager / RAEM ChromaDB bridge
    pipeline/            the notebook's ported RAEM pipeline (agents, memory,
                          runner, demo mode) — reused unchanged, drives
                          TradingAgents' own tools/dataflows directly
    services/            market_data (cached quote facade), analysis_store (Mongo)
    workers/             scheduler (watchlist heartbeat), celery_app/tasks
                          (optional background analysis)
  tradingagents/         the multi-agent AI engine + llm_clients factory
                          (vendored, unchanged) — the ONLY LLM provider layer
frontend/                Next.js 15 dashboard (App Router, TS, Tailwind v4)
  src/app/                routes: /, /analysis, /analysis/[id], /watchlist,
                          /news, /memory, /settings
  src/components/         layout, ui primitives, analysis/market/memory panels
  src/lib/                typed API client, WS client, types mirroring the
                          backend's Pydantic schemas
  src/hooks/               useHealth, useAnalysis, useAnalysisSocket, useLiveFeed, useWatchlist
docker-compose.yml       mongo · redis · api · worker · celery_worker · web
.env.example
```

**Reuse, not rewrite:** `tradingagents/` (agent graph, prompts, debate,
dataflows, LLM factory) and `pipeline/` (the notebook's RAEM + ChromaDB
memory, faithfully ported stage-for-stage) are reused as-is.
`ai_engine/orchestrator.py` only wraps the reused `PipelineRunner` to
translate its events into a typed stream and persist results — it makes no
LLM calls of its own.

---

## API

```
GET  /api/v1/health                        service status
POST /api/v1/analysis                       run (sync) or {"background": true} -> ids
GET  /api/v1/analysis/{id}                  full structured AnalysisResponse
GET  /api/v1/analysis/{id}/trace            execution trace (spans/timings)
GET  /api/v1/analysis/{id}/agents           per-agent outputs
GET  /api/v1/analysis/ticker/{t}/history    recent analyses for a ticker
GET  /api/v1/memory/health                  ChromaDB collection health
GET  /api/v1/memory/collections             list memory collections
POST /api/v1/memory/search                  semantic search over memory
GET  /api/v1/stocks/...                     lightweight cached quotes
WS   /ws                                     global event stream
WS   /ws/analysis/{id}                       live event stream for one run
```

---

*Research and educational tooling. Not investment advice.*
