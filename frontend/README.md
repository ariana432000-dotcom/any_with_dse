# AInvest Frontend

A local, production-ready Next.js 15 dashboard for the AInvest trading research
platform — TradingAgents multi-agent analysis, RAEM episodic memory, live
market data, and a real-time event stream, all served by the FastAPI backend
in `../backend`. No login: this is a single-local-user app.

## Stack

- **Next.js 15** (App Router, React 19, TypeScript)
- **Tailwind CSS v4** — dark-by-default "trading terminal" theme with a light-mode toggle
- **Recharts** for price charts
- **lucide-react** for icons
- Native `fetch` + `WebSocket` — no extra data-fetching or state library needed

## Quick start

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. That's it — no environment file is required to get
started: the app defaults to `http://localhost:8000` for the backend, which
matches `docker compose up` / `python run.py` in `../backend` out of the box.

If your backend runs somewhere else, copy `.env.local.example` to `.env.local`
and change `NEXT_PUBLIC_API_URL`.

## Scripts

| Command         | What it does                        |
|------------------|--------------------------------------|
| `npm run dev`    | Start the dev server on :3000        |
| `npm run build`  | Production build (type-checked + linted) |
| `npm run start`  | Serve the production build           |
| `npm run lint`   | ESLint                               |

## Pages

| Route            | What it shows |
|-------------------|---------------|
| `/`                | Dashboard: backend/AI/memory status, watchlist, live activity feed |
| `/analysis`        | Run a new analysis; browse a ticker's analysis history |
| `/analysis/[id]`   | Full analysis detail — agents, AI debate, risk/portfolio manager, recommendation, RAEM memory hits, live progress while running |
| `/watchlist`       | Manage tickers (saved in `localStorage`), live quotes, price chart + indicators |
| `/news`            | Keyless per-ticker headlines |
| `/memory`          | Browse/search the 8 ChromaDB memory collections (RAEM episodic memory, market memory, etc.) |
| `/settings`        | Theme, backend connection status, AI provider/model in use |

## Structure

```
src/
  app/                 routes (App Router) — one folder per page above
  components/
    layout/            Sidebar, Topbar, AppShell (responsive shell)
    ui/                 Card, Badge, Button, StatCard, SignalGauge, loading/empty/error states
    analysis/            AnalysisForm, AgentCard, DebatePanel, RecommendationPanel, RiskPortfolioPanel, AnalysisProgress (live), AnalysisMemoryPanel, AnalysisHistoryTable
    market/              PriceChart, WatchlistTable, AddTickerForm, NewsList
    memory/              MemoryCollectionCard, MemorySearchForm, MemoryRecordCard
    providers/           ThemeProvider (dark/light, localStorage)
  hooks/                useHealth, useAnalysis, useAnalysisSocket, useLiveFeed, useWatchlist
  lib/
    api.ts               typed REST client — one function per backend route
    ws.ts                small auto-reconnecting WebSocket wrapper
    types.ts             TypeScript types mirroring the backend's Pydantic schemas 1:1
    utils.ts, constants.ts
```

## Backend integration

Every function in `src/lib/api.ts` maps directly to a route in
`../backend/app/api/routes/*.py` — see that file for the exact endpoint list.
Live updates use the backend's two WebSocket endpoints: `/ws` (global activity
feed, used on the dashboard) and `/ws/analysis/{id}` (per-run progress, used
on the analysis detail page while a run is in flight).

No authentication headers are sent or required — the backend has none.
