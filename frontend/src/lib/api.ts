/**
 * Typed API client for the AInvest FastAPI backend.
 *
 * Base URL comes from NEXT_PUBLIC_API_URL (see .env.local.example), defaulting
 * to http://localhost:8000 for local development against `docker compose up`
 * or `python run.py`. Every function here maps 1:1 to a route in
 * backend/app/api/routes/*.py.
 */
import type {
  AnalysisAgentsResponse,
  AnalysisHistoryResponse,
  AnalysisResponse,
  BacktestResponse,
  DatasetListResponse,
  DatasetRowsResponse,
  DispatchBackgroundResponse,
  ExecutionRequest,
  Health,
  HistoryResponse,
  MemoryCollection,
  MemoryHealth,
  MemoryRecord,
  NewsResponse,
  PaperPortfolio,
  PaperTradeExecuteResponse,
  PaperTradesResponse,
  QuoteResponse,
  RetrievalQuery,
  RetrievedMemory,
  WatchlistResponse,
} from "./types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") || "http://localhost:8000";
export const API_V1 = `${API_BASE_URL}/api/v1`;

export function wsBaseUrl(): string {
  return API_BASE_URL.replace(/^http/, "ws");
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(
  path: string,
  init?: RequestInit & { timeoutMs?: number },
): Promise<T> {
  const { timeoutMs = 30_000, ...rest } = init ?? {};
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  let res: Response;
  try {
    res = await fetch(`${API_V1}${path}`, {
      ...rest,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(rest.headers ?? {}),
      },
      cache: "no-store",
    });
  } catch (err) {
    clearTimeout(timeout);
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(
        `Request to ${path} timed out after ${timeoutMs}ms`,
        0,
      );
    }
    throw new ApiError(
      `Could not reach the AInvest backend at ${API_BASE_URL}. Is it running?`,
      0,
      err,
    );
  } finally {
    clearTimeout(timeout);
  }

  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text().catch(() => undefined);
    }
    const message =
      (detail && typeof detail === "object" && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : undefined) || `${res.status} ${res.statusText}`;
    throw new ApiError(message, res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------
export const healthApi = {
  get: () => request<Health>("/health", { timeoutMs: 8_000 }),
};

// ---------------------------------------------------------------------------
// Analysis
// ---------------------------------------------------------------------------
export const analysisApi = {
  /** Run synchronously — resolves only once the full pipeline finishes. */
  runSync: (req: Omit<ExecutionRequest, "background">) =>
    request<AnalysisResponse>("/analysis", {
      method: "POST",
      body: JSON.stringify({ ...req, background: false }),
      timeoutMs: 10 * 60_000, // agent pipelines can legitimately take minutes
    }),

  /** Dispatch in the background — returns immediately with ids to poll/stream. */
  runBackground: (req: Omit<ExecutionRequest, "background">) =>
    request<DispatchBackgroundResponse>("/analysis", {
      method: "POST",
      body: JSON.stringify({ ...req, background: true }),
      timeoutMs: 15_000,
    }),

  get: (analysisId: string) =>
    request<AnalysisResponse>(`/analysis/${encodeURIComponent(analysisId)}`),

  getTrace: (analysisId: string) =>
    request<Record<string, unknown>>(
      `/analysis/${encodeURIComponent(analysisId)}/trace`,
    ),

  getAgents: (analysisId: string) =>
    request<AnalysisAgentsResponse>(
      `/analysis/${encodeURIComponent(analysisId)}/agents`,
    ),

  tickerHistory: (ticker: string, limit = 20) =>
    request<AnalysisHistoryResponse>(
      `/analysis/ticker/${encodeURIComponent(ticker)}/history?limit=${limit}`,
    ),
};

// ---------------------------------------------------------------------------
// Memory
// ---------------------------------------------------------------------------
export const memoryApi = {
  health: () => request<MemoryHealth>("/memory/health", { timeoutMs: 8_000 }),

  listCollections: () =>
    request<{ collections: string[] }>("/memory/collections"),

  search: (query: RetrievalQuery) =>
    request<RetrievedMemory[]>("/memory/search", {
      method: "POST",
      body: JSON.stringify(query),
    }),

  recent: (collection: MemoryCollection, limit = 10, ticker?: string) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (ticker) params.set("ticker", ticker);
    return request<RetrievedMemory[]>(
      `/memory/${collection}/recent?${params.toString()}`,
    );
  },

  get: (collection: MemoryCollection, memoryId: string) =>
    request<MemoryRecord>(
      `/memory/${collection}/${encodeURIComponent(memoryId)}`,
    ),

  updateOutcome: (
    collection: MemoryCollection,
    memoryId: string,
    outcome: string,
    experienceScore?: number,
  ) => {
    const params = new URLSearchParams({ outcome });
    if (experienceScore !== undefined) {
      params.set("experience_score", String(experienceScore));
    }
    return request<{ updated: boolean; memory_id: string; outcome: string }>(
      `/memory/${collection}/${encodeURIComponent(memoryId)}/outcome?${params.toString()}`,
      { method: "PATCH" },
    );
  },

  delete: (collection: MemoryCollection, memoryId: string) =>
    request<{ deleted: boolean; memory_id: string }>(
      `/memory/${collection}/${encodeURIComponent(memoryId)}`,
      { method: "DELETE" },
    ),
};

// ---------------------------------------------------------------------------
// Watchlist (server-side; shared with the scheduled dataset job)
// ---------------------------------------------------------------------------
export const watchlistApi = {
  list: () => request<WatchlistResponse>("/watchlist", { timeoutMs: 8_000 }),

  add: (ticker: string) =>
    request<WatchlistResponse>("/watchlist", {
      method: "POST",
      body: JSON.stringify({ ticker }),
      timeoutMs: 8_000,
    }),

  remove: (ticker: string) =>
    request<WatchlistResponse>(`/watchlist/${encodeURIComponent(ticker)}`, {
      method: "DELETE",
      timeoutMs: 8_000,
    }),
};

// ---------------------------------------------------------------------------
// Dataset (CSV export built by the scheduled dataset job)
// ---------------------------------------------------------------------------
export const datasetApi = {
  list: () => request<DatasetListResponse>("/dataset", { timeoutMs: 10_000 }),

  rows: (ticker: string, limit = 500) =>
    request<DatasetRowsResponse>(
      `/dataset/${encodeURIComponent(ticker)}?limit=${limit}`,
      { timeoutMs: 15_000 },
    ),

  downloadUrl: (ticker: string) =>
    `${API_V1}/dataset/${encodeURIComponent(ticker)}/download`,
};

// ---------------------------------------------------------------------------
// Backtest / accuracy tracker
// ---------------------------------------------------------------------------
export const backtestApi = {
  all: (limit = 1000) =>
    request<BacktestResponse>(`/backtest?limit=${limit}`, { timeoutMs: 20_000 }),

  forTicker: (ticker: string, limit = 500) =>
    request<BacktestResponse>(
      `/backtest/${encodeURIComponent(ticker)}?limit=${limit}`,
      { timeoutMs: 20_000 },
    ),
};

// ---------------------------------------------------------------------------
// Paper trading (simulated portfolio, no real money)
// ---------------------------------------------------------------------------
export const paperTradingApi = {
  portfolio: () => request<PaperPortfolio>("/paper-trading/portfolio", { timeoutMs: 20_000 }),

  trade: (ticker: string, side: "BUY" | "SELL", shares: number) =>
    request<PaperTradeExecuteResponse>("/paper-trading/trade", {
      method: "POST",
      body: JSON.stringify({ ticker, side, shares }),
      timeoutMs: 20_000,
    }),

  trades: (limit = 50) =>
    request<PaperTradesResponse>(`/paper-trading/trades?limit=${limit}`, { timeoutMs: 10_000 }),

  reset: (startingCash?: number) =>
    request<PaperPortfolio>("/paper-trading/reset", {
      method: "POST",
      body: JSON.stringify({ starting_cash: startingCash ?? null }),
      timeoutMs: 10_000,
    }),
};

// ---------------------------------------------------------------------------
// Market data (stocks)
// ---------------------------------------------------------------------------
export const stocksApi = {
  quote: (ticker: string) =>
    request<QuoteResponse>(`/stocks/${encodeURIComponent(ticker)}/quote`, {
      timeoutMs: 20_000,
    }),

  history: (ticker: string, days = 220) =>
    request<HistoryResponse>(
      `/stocks/${encodeURIComponent(ticker)}/history?days=${days}`,
      { timeoutMs: 20_000 },
    ),

  news: (ticker: string, limit = 8) =>
    request<NewsResponse>(
      `/stocks/${encodeURIComponent(ticker)}/news?limit=${limit}`,
      { timeoutMs: 20_000 },
    ),
};
