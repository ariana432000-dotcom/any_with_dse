# ChromaDB Memory Integration (Phase 2)

Production ChromaDB memory layer for the AInvest platform. It **wraps the
notebook's existing RAEM implementation** as the episodic memory engine and adds
a unified `MemoryManager` over eight collections. Nothing in TradingAgents, RAEM,
or FastAPI was rewritten. (This app has no auth — single local user.)

> Superseded by `ai_engine/orchestrator.py` (Phase 3): the execution flow
> described below as `services/ai_engine.py` was an early draft of that same
> wiring and has since been removed as dead code — the Orchestrator is what
> actually runs today.

## What was added (new code only where missing)

```
app/ai_engine/memory/
    __init__.py          # MemoryManager (unified interface) + get_memory_manager()
    memory_manager.py    # re-export of MemoryManager (per requested structure)
    chroma_manager.py    # sole owner of the persistent client + 8 collections
    embeddings.py        # configurable provider: ollama | openai | sentence-transformers
    retrieval.py         # semantic + filters (ticker/date/agent/regime/tags/threshold)
    storage.py           # store / update-metadata / delete
    schemas.py           # MemoryRecord (full 16-field schema) + Collection enum
app/api/routes/memory.py     # memory API (all via MemoryManager)
app/api/routes/analysis.py   # /analysis/run — full agentic flow with memory
tests/test_memory_integration.py   # 10 integration tests (real Chroma, offline embedder)
```

## What was reused (unchanged)

- **`app/pipeline/memory.py`** — the notebook's RAEM: `classify_regime`,
  `backfill_pending_outcomes`, `retrieve_similar_episodes`, `save_episode`,
  `reflect_on_regime_transition`, experience/outcome logic. Only its `connect()`
  was pointed at the shared `ChromaManager` client (with a stand-alone fallback),
  so RAEM and the platform use **one** persistent database and the configurable
  embedder — no logic changed.
- **`tradingagents/`** — untouched.

## Collections (8, independent)

`episodic_memory` · `market_memory` · `conversation_memory` · `portfolio_memory`
· `research_memory` · `news_memory` · `execution_history` · `agent_reasoning`

Created automatically on startup (`MemoryManager.ensure_ready()`), and on first
use. RAEM's episodic memory maps onto `episodic_memory`; its news corpus onto
`news_memory`.

## MemoryManager — the only entry point

`store_memory`, `store_many`, `retrieve_memory`, `retrieve_recent`,
`retrieve_similar`, `retrieve_by_ticker`, `retrieve_by_regime`,
`retrieve_by_tags`, `update_outcome`, `delete_memory`, `get_memory`,
`list_collections`, `health_check`, `ensure_ready`, and `.raem` (the delegated
RAEM engine). No route or agent touches ChromaDB directly.

## Execution flow (now wired in `ai_engine/orchestrator.py`)

```
ticker → fetch market data → retrieve memories (MemoryManager)
       → inject context → run TradingAgents/RAEM pipeline
       (analysts → bull/bear debate → RAEM retrieval → trader
        → risk debate → portfolio manager → final recommendation)
       → store execution back into ChromaDB (execution_history + agent_reasoning)
```

RAEM already performs its own episodic retrieve-before / store-after inside the
pipeline; the service adds the cross-collection generic memory and the durable
execution record so the whole platform accumulates memory.

## Embeddings (configurable, `.env`)

```
EMBEDDING_PROVIDER=ollama            # ollama | openai | sentence-transformers
EMBEDDING_MODEL_OPENAI=text-embedding-3-small
EMBEDDING_MODEL_ST=all-MiniLM-L6-v2
```

No provider-specific code lives in business logic; add a provider by subclassing
`EmbeddingProvider` and registering it in `embeddings._REGISTRY`.

## Persistence & Docker

- `CHROMA_DB_PATH=/data/chroma` (never in-memory). Directory auto-created.
- `docker-compose.yml`: the `chromadata` named volume is mounted into **both**
  `api` and `worker` at `/data/chroma`, so memory survives container restarts.

## Logging

Every store logs the document id, collection, and latency; every retrieval logs
the result count, collection, top similarity score, and latency; the embedding
provider/model is logged on selection; errors are logged with context.

## Tests

```
cd backend && pytest tests/test_memory_integration.py -v
```

10 tests, all passing: store, retrieve, semantic search, ticker filter, regime
filter, outcome update, delete, health/list, RAEM-shares-client, and
persistence-after-restart. They use a real persistent ChromaDB with a
deterministic offline embedder, so they need no Ollama/OpenAI.

*Not investment advice.*
