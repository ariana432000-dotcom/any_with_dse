/**
 * Types mirroring the backend's Pydantic schemas 1:1.
 *
 * Sources (backend):
 *   app/ai_engine/state.py        -> ExecutionRequest / ExecutionState / *
 *   app/ai_engine/events.py       -> EventType / ExecutionEvent
 *   app/ai_engine/memory/schemas.py -> Collection / MemoryRecord / RetrievedMemory / MemoryHealth
 *   app/models/analysis.py        -> AnalysisResponse / AgentView
 *   app/models/schemas.py         -> Health
 *   app/services/market_data.py   -> quote / history / news shapes
 */

// ---------------------------------------------------------------------------
// Signals / status
// ---------------------------------------------------------------------------
export type Signal = "BUY" | "SELL" | "HOLD" | "N/A";

export type ExecutionStatus =
  | "PENDING"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "PARTIAL";

// ---------------------------------------------------------------------------
// Analysis request / response
// ---------------------------------------------------------------------------
export interface ExecutionRequest {
  ticker: string;
  date?: string | null;
  asset_type?: string;
  provider?: string | null;
  investment_rounds?: number | null;
  risk_rounds?: number | null;
  background?: boolean;
}

export interface DispatchBackgroundResponse {
  analysis_id: string;
  task_id: string | null;
  status: ExecutionStatus;
}

export interface MarketState {
  ticker: string;
  provider: string;
  latest_close: number | null;
  change_pct: number | null;
  indicators: Record<string, number | string>;
  rows: OhlcvRow[];
  news: Record<string, unknown>[];
  fetched_at: string;
  ok: boolean;
  error: string | null;
}

export interface MemoryHit {
  memory_id: string;
  ticker: string;
  timestamp: string;
  market_regime: string;
  decision: string;
  outcome: string;
  similarity: number | null;
}

export interface MemoryState {
  regime: string;
  hits: MemoryHit[];
  injected_context: string;
  episodic_count: number;
}

export interface AgentView {
  name: string;
  signal: Signal;
  confidence: number;
  analysis: string;
  latency_ms: number;
  ok: boolean;
  error: string | null;
}

export interface DebateTurn {
  speaker: string;
  side: string;
  round: number;
  content: string;
}

export interface DebateState {
  turns: DebateTurn[];
  winner: string;
  summary: string;
}

export interface RiskState {
  rating: string;
  position_sizing: string;
  stop_loss: number | null;
  take_profit: number | null;
  summary: string;
}

export interface PortfolioState {
  signal: Signal;
  allocation_pct: number | null;
  rationale: string;
}

export interface MacroState {
  regime: string; // RISK_OFF_HIGH_VOL / RISK_ON_LOW_VOL / RATES_RISING / RATES_FALLING / NEUTRAL_MACRO
  report: string;
  vix: number | null;
  vix_avg: number | null;
  tnx: number | null;
  tnx_avg: number | null;
  dxy: number | null;
  dxy_avg: number | null;
  // Populated instead of vix/tnx/dxy for DSE tickers (see backend
  // fetch_dse_macro_snapshot) -- the DSEX broad index + its realized
  // volatility, since VIX/10Y/DXY are US indicators.
  dsex: number | null;
  dsex_avg: number | null;
  dsex_volatility_pct: number | null;
}

export interface PostMortemState {
  lessons: string;
  episodes_reviewed: number;
}

export interface VerifierState {
  status: string; // VERIFIED / FLAGGED
  notes: string;
  raw_signal: Signal;
  effective_signal: Signal;
  auto_overridden: boolean;
}

export interface PriceOutlookState {
  days: number;
  low: number | null;
  high: number | null;
  daily_volatility_pct: number | null;
  basis: string;
}

export interface RecommendationState {
  signal: Signal;
  confidence: number;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  time_horizon: string;
  bull_case: string;
  bear_case: string;
  reasoning: string;
  summary: string;
  currency: string;
  outlook_3d: PriceOutlookState | null;
}

export interface ExecutionMetadata {
  provider: string;
  total_latency_ms: number;
  agent_count: number;
  failed_agents: string[];
  memory_hits: number;
  event_count: number;
  tokens: number;
  started_at: string;
  finished_at: string;
}

// ---------------------------------------------------------------------------
// Pipeline flow (per-agent input/output — powers the flow diagram view)
// ---------------------------------------------------------------------------
export interface PipelineStep {
  stage: string; // matches backend app/pipeline/runner.py STAGES ids
  label: string;
  input: Record<string, unknown> | string;
  output: Record<string, unknown> | string;
  started_at: string;
  finished_at: string;
  latency_ms: number;
}

export interface AnalysisResponse {
  analysis_id: string;
  ticker: string;
  status: ExecutionStatus;
  created_at: string;

  market: MarketState | null;
  technical: AgentView | null;
  fundamental: AgentView | null;
  news: AgentView | null;
  sentiment: AgentView | null;
  memory: MemoryState | null;
  debate: DebateState | null;
  risk: RiskState | null;
  portfolio: PortfolioState | null;
  macro: MacroState | null;
  post_mortem: PostMortemState | null;
  verifier: VerifierState | null;
  recommendation: RecommendationState | null;
  confidence: number;
  reasoning: string;
  metadata: ExecutionMetadata;
  pipeline: PipelineStep[];
  error: string | null;
}

export interface AnalysisHistoryItem {
  analysis_id?: string;
  _id?: string;
  ticker: string;
  status: ExecutionStatus;
  created_at?: string;
  updated_at?: string;
  confidence?: number;
  recommendation?: RecommendationState | null;
  [key: string]: unknown;
}

export interface AnalysisHistoryResponse {
  ticker: string;
  analyses: AnalysisHistoryItem[];
}

export interface AnalysisAgentsResponse {
  analysis_id: string;
  agents: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Watchlist (server-side, shared with the scheduled dataset job)
// ---------------------------------------------------------------------------
export interface WatchlistResponse {
  tickers: string[];
}

// ---------------------------------------------------------------------------
// Dataset (CSV export built by the scheduled dataset job)
// ---------------------------------------------------------------------------
export interface DatasetSummary {
  ticker: string;
  rows: number;
  updated_at: string;
}

export interface DatasetListResponse {
  datasets: DatasetSummary[];
}

export interface DatasetRow {
  date: string;
  created_at: string;
  analysis_id: string;
  ticker: string;
  signal: string;
  effective_signal: string;
  confidence: string;
  regime: string;
  macro_regime: string;
  verifier_status: string;
  auto_overridden: string;
  rsi: string;
  macd: string;
  pe_ratio: string;
  eps_ttm: string;
  news_sentiment: string;
  entry_price: string;
  stop_loss: string;
  take_profit: string;
  post_mortem_episodes_reviewed: string;
  reasoning_snippet: string;
}

export interface DatasetRowsResponse {
  ticker: string;
  rows: DatasetRow[];
}

// ---------------------------------------------------------------------------
// Backtest / accuracy tracker (aggregated over RESOLVED RAEM episodes)
// ---------------------------------------------------------------------------
export interface BacktestBucket {
  count: number;
  wins: number;
  losses: number;
  flats: number;
  win_rate: number;
  avg_pnl_pct: number;
}

export interface BacktestCurvePoint {
  trade_date: string;
  ticker: string;
  signal: string;
  regime: string;
  macro_regime: string;
  verifier_status: string;
  pnl_pct: number;
  cumulative_pnl_pct: number;
  outcome_label: string;
}

export interface BacktestResponse {
  ticker: string | null;
  total_episodes: number;
  resolved_episodes: number;
  pending_episodes: number;
  wins: number;
  losses: number;
  flats: number;
  win_rate: number;
  avg_pnl_pct: number;
  by_signal: Record<string, BacktestBucket>;
  by_regime: Record<string, BacktestBucket>;
  by_macro_regime: Record<string, BacktestBucket>;
  by_verifier_status: Record<string, BacktestBucket>;
  curve: BacktestCurvePoint[];
}

// ---------------------------------------------------------------------------
// Paper trading (simulated portfolio, no real money)
// ---------------------------------------------------------------------------
export interface PaperPosition {
  ticker: string;
  shares: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
}

export interface PaperPortfolio {
  cash: number;
  starting_cash: number;
  realized_pnl: number;
  unrealized_pnl: number;
  market_value: number;
  equity: number;
  total_return_pct: number;
  positions: PaperPosition[];
  updated_at: string | null;
}

export interface PaperTrade {
  id?: string;
  ticker: string;
  side: string;
  shares: number;
  price: number;
  value: number;
  realized_pnl: number;
  cash_after: number;
  created_at: string;
}

export interface PaperTradeExecuteResponse {
  portfolio: PaperPortfolio;
  trade: PaperTrade;
}

export interface PaperTradesResponse {
  trades: PaperTrade[];
}

// ---------------------------------------------------------------------------
// Live execution events (WebSocket)
// ---------------------------------------------------------------------------
export type EventType =
  | "STARTED"
  | "VALIDATING"
  | "FETCHING_MARKET_DATA"
  | "RETRIEVING_MEMORY"
  | "RUNNING_TECHNICAL_AGENT"
  | "RUNNING_FUNDAMENTAL_AGENT"
  | "RUNNING_NEWS_AGENT"
  | "RUNNING_MACRO_AGENT"
  | "RUNNING_SENTIMENT_AGENT"
  | "RUNNING_DEBATE"
  | "RUNNING_POST_MORTEM_AGENT"
  | "RUNNING_RISK_MANAGER"
  | "RUNNING_PORTFOLIO_MANAGER"
  | "RUNNING_VERIFIER_AGENT"
  | "RUNNING_CIO"
  | "GENERATING_RECOMMENDATION"
  | "SAVING_RESULTS"
  | "AGENT_MESSAGE"
  | "COMPLETED"
  | "ERROR";

export interface ExecutionEventPayload {
  channel?: "analysis";
  type: EventType | "SUBSCRIBED" | "SNAPSHOT" | "connected" | "pong";
  analysis_id?: string;
  ticker?: string;
  message?: string;
  progress?: number;
  data?: Record<string, unknown>;
  ts?: string;
  status?: string;
}

// ---------------------------------------------------------------------------
// Memory (ChromaDB / RAEM)
// ---------------------------------------------------------------------------
export const MEMORY_COLLECTIONS = [
  "episodic_memory",
  "market_memory",
  "conversation_memory",
  "portfolio_memory",
  "research_memory",
  "news_memory",
  "execution_history",
  "agent_reasoning",
] as const;

export type MemoryCollection = (typeof MEMORY_COLLECTIONS)[number];

export interface MemoryRecord {
  memory_id: string;
  ticker: string;
  timestamp: string;
  market_regime: string;
  agent_name: string;
  summary: string;
  reasoning: string;
  decision: string;
  confidence: number;
  risk: string;
  metadata: Record<string, unknown>;
  tags: string[];
  source: string;
  version: string;
  outcome: string;
  experience_score: number;
}

export interface RetrievedMemory {
  record: MemoryRecord;
  similarity: number | null;
  distance: number | null;
}

export interface RetrievalQuery {
  text?: string | null;
  collection: MemoryCollection;
  top_k?: number;
  ticker?: string | null;
  agent_name?: string | null;
  market_regime?: string | null;
  tags?: string[] | null;
  date_from?: string | null;
  date_to?: string | null;
  similarity_threshold?: number | null;
  where?: Record<string, unknown> | null;
}

export interface MemoryHealth {
  ok: boolean;
  path: string;
  embedding_provider: string;
  embedding_model: string;
  collections: Record<string, number>;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Market data
// ---------------------------------------------------------------------------
export interface OhlcvRow {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
}

export interface QuoteResponse {
  ticker: string;
  price: number | null;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  volume?: number | null;
  change_pct: number | null;
  date?: string | null;
}

export interface HistoryResponse {
  ticker: string;
  rows: OhlcvRow[];
  indicators: Record<string, number>;
  latest_close: number | null;
  provider: string;
  fetched_at: string;
}

export interface NewsItem {
  title: string;
  source: string;
  url?: string | null;
}

export interface NewsResponse {
  ticker: string;
  items: NewsItem[];
}

export interface FundamentalsCheckResponse {
  ticker: string;
  ok: boolean | null;
  status: string;
  parsed: {
    pe_ratio: string | null;
    eps: string | null;
    market_cap: string | null;
    dividend_yield: string | null;
  };
  all_fields: Record<string, string>;
  raw_response: string;
}

export interface DseReportsListResponse {
  ticker: string;
  uploaded_fiscal_years: string[];
  extracted_fiscal_years: string[];
  pending_extraction: string[];
}

export interface DseReportUploadResponse {
  ticker: string;
  fiscal_year: string;
  saved_to: string;
  bytes: number;
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------
export interface ChromaHealthDetail {
  ok: boolean;
  collections?: Record<string, number>;
  embedding_provider?: string;
  error?: string;
}

export interface Health {
  status: "ok" | "degraded";
  services: {
    mongo: boolean;
    redis: boolean;
    chroma: ChromaHealthDetail;
  };
  ai_configured: boolean;
  ai_provider: string;
  ai_model: string;
}
