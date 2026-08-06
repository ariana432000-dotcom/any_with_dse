# Deploying: Vercel (frontend) + Railway (backend + DBs)

## Architecture
```
Vercel (frontend, Next.js)  --https/wss-->  Railway (api service, FastAPI)
                                                  |-- MongoDB (Railway plugin)
                                                  |-- Redis (Railway plugin)
                                                  '-- ChromaDB (Volume-backed, embedded in api)
```
`worker` and `celery_worker` (docker-compose.yml) are optional — skip both for
the simplest/cheapest setup; background analysis falls back to running
in-process, and the watchlist heartbeat just won't refresh automatically.

---

## Part 1 — Backend + databases on Railway

1. **Push this repo to GitHub** (Railway deploys from a GitHub repo).

2. **New Railway project** → **Add MongoDB** (from Railway's plugin/template
   list) → **Add Redis** (same). Each becomes its own service with its own
   connection-string variable (typically `MONGO_URL` / `REDIS_URL` — check
   the exact name in that service's **Variables** tab on Railway, naming can
   vary slightly by template version).

3. **Add a new service** → **Deploy from GitHub repo** → same repo, but set
   **Root Directory** to `backend`. Railway detects `backend/Dockerfile`
   automatically and builds from it — `docker-compose.yml` is not used here.

4. **Add a Volume** to this service (Settings → Volumes), mount it at
   `/data/chroma`. Without this, ChromaDB's memory is wiped on every
   redeploy/restart.

5. **Environment variables** for the `api` service (Settings → Variables) —
   copy every key from `.env.example` and fill in real values, plus wire the
   two database services using Railway's cross-service reference syntax:
   ```
   MONGO_URI=${{MongoDB.MONGO_URL}}
   REDIS_URL=${{Redis.REDIS_URL}}
   CHROMA_DB_PATH=/data/chroma
   RAEM_LLM_PROVIDER=anthropic
   RAEM_LLM_MODEL=claude-sonnet-5
   ANTHROPIC_API_KEY=...
   FMP_API_KEY=...
   FINNHUB_API_KEY=...
   BACKEND_CORS_ORIGINS=https://YOUR-APP.vercel.app,http://localhost:3000
   ```
   (`${{ServiceName.VAR}}` is Railway's syntax for referencing another
   service's variable — replace `MongoDB`/`Redis` with whatever your two
   services are actually named in your project.)
   You won't have the real Vercel URL for `BACKEND_CORS_ORIGINS` until Part 2
   — come back and update it after your first Vercel deploy.

6. **Deploy.** Once it's up, Railway gives the service a public domain
   (Settings → Networking → Generate Domain) — this is your backend URL,
   e.g. `https://ainvest-api-production.up.railway.app`. Test it:
   `curl https://<that-domain>/api/v1/health`.

---

## Part 2 — Frontend on Vercel

1. **New Project** on Vercel → import the same GitHub repo → set
   **Root Directory** to `frontend`. Vercel auto-detects Next.js; no
   Dockerfile involved (Vercel ignores `frontend/Dockerfile` entirely — it
   has its own native Next.js build pipeline).

2. **Environment variable**:
   ```
   NEXT_PUBLIC_API_URL=https://<your-railway-backend-domain>
   ```

3. **Deploy.** Vercel gives you a public URL, e.g.
   `https://ainvest.vercel.app`.

WebSocket note: the frontend derives its `wss://` URL from
`NEXT_PUBLIC_API_URL` automatically (`lib/api.ts`'s `wsBaseUrl()` swaps
`http`→`ws`), so no separate WebSocket URL variable is needed — Railway's
public domains support WebSockets over the same HTTPS domain.

---

## Part 3 — Connect them

Go back to the Railway `api` service's variables and update:
```
BACKEND_CORS_ORIGINS=https://ainvest.vercel.app
```
(use your actual Vercel domain). Redeploy the Railway service for the change
to take effect. Without this, the browser will block every API call from
the Vercel-hosted frontend with a CORS error.

---

## Fixed while wiring this up
`backend/Dockerfile` hardcoded `--port 8000`. Railway assigns a dynamic
`$PORT` and routes traffic to it — a fixed port silently breaks public
networking there. Changed to `--port ${PORT:-8000}` (still defaults to 8000
for local `docker run`/`docker compose up`, where `$PORT` is unset).

## Sanity checklist after deploying
- [ ] `https://<railway-domain>/api/v1/health` returns `{"status": "ok", ...}`
- [ ] `https://<railway-domain>/api/v1/health` shows `mongo: true`, `redis: true`
- [ ] Vercel site loads and the Settings page shows AI engine = `anthropic` / `claude-sonnet-5`
- [ ] Run one analysis end-to-end from the Vercel UI and confirm the live
      WebSocket progress stream shows up (confirms `wss://` is reachable)
