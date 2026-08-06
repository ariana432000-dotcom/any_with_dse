/**
 * Single source of truth for every stage the backend pipeline can run
 * (mirrors backend/app/pipeline/runner.py STAGES 1:1 — same ids).
 * Used by both PipelineFlowPanel (the flow-diagram view) and StageTabs
 * (the per-stage tabbed view) so the two never drift apart.
 */
export interface StageMeta {
  id: string;
  label: string;
  group: string;
  blurb: string;
}

export const STAGE_META: StageMeta[] = [
  { id: "outcome_backfill", label: "Outcome Backfill", group: "setup",
    blurb: "Resolves older PENDING episodes with today's close price." },
  { id: "fundamentals", label: "Fundamentals Analyst", group: "analysts",
    blurb: "P/E, EPS, cash flow, debt — balance sheet + income statement." },
  { id: "market", label: "Market Analyst", group: "analysts",
    blurb: "RSI, MACD, 50-day SMA, Bollinger Bands." },
  { id: "news", label: "News Analyst", group: "analysts",
    blurb: "Headline sentiment + ingests articles into the news RAG corpus." },
  { id: "sentiment", label: "Sentiment Analyst", group: "analysts",
    blurb: "Social / market sentiment score." },
  { id: "macro_regime", label: "Macro Regime Analyst", group: "analysts",
    blurb: "VIX / 10Y yield / DXY -> market-wide risk regime." },
  { id: "investment_debate", label: "Bull vs Bear Debate", group: "debate",
    blurb: "Bull and Bear analysts argue in alternating rounds." },
  { id: "investment_facilitator", label: "Investment Facilitator", group: "debate",
    blurb: "Declares a debate winner + a BUY/SELL/HOLD recommendation." },
  { id: "memory", label: "Episodic Memory (RAEM)", group: "memory",
    blurb: "Retrieves similar past episodes + regime-transition reflection." },
  { id: "post_mortem", label: "Post-Mortem Review", group: "memory",
    blurb: "Cross-regime self-critique over all RESOLVED past episodes." },
  { id: "trader", label: "Trader Proposal", group: "trader",
    blurb: "Turns the debate + memory context into a concrete plan." },
  { id: "risk_debate", label: "Risk Debate", group: "risk",
    blurb: "Aggressive / Conservative / Neutral debate the risk profile." },
  { id: "risk_facilitator", label: "Risk Facilitator", group: "risk",
    blurb: "Position sizing, stop-loss / take-profit, risk rating." },
  { id: "portfolio_manager", label: "Portfolio Manager", group: "decision",
    blurb: "Final BUY / SELL / HOLD call." },
  { id: "decision_verifier", label: "Decision Verifier", group: "decision",
    blurb: "Rule-based + numeric + LLM sanity check on the final call." },
  { id: "save_episode", label: "Save Episode", group: "save",
    blurb: "Writes this run back into episodic memory for future retrieval." },
];

export const STAGE_GROUPS: { id: string; label: string }[] = [
  { id: "setup", label: "Setup" },
  { id: "analysts", label: "Analysts — run in parallel" },
  { id: "debate", label: "Investment debate" },
  { id: "memory", label: "RAEM memory — retrieval + post-mortem" },
  { id: "trader", label: "Trader" },
  { id: "risk", label: "Risk debate" },
  { id: "decision", label: "Final decision" },
  { id: "save", label: "Save episode" },
];

// [from, to, isFeedback?]
export const STAGE_EDGES: [string, string, boolean?][] = [
  ["fundamentals", "investment_debate"], ["market", "investment_debate"],
  ["news", "investment_debate"], ["sentiment", "investment_debate"],
  ["investment_debate", "investment_facilitator"],
  ["market", "memory"], ["macro_regime", "memory"],
  ["memory", "post_mortem"],
  ["investment_facilitator", "trader"], ["memory", "trader"], ["post_mortem", "trader"],
  ["fundamentals", "trader"], ["market", "trader"],
  ["trader", "risk_debate"], ["fundamentals", "risk_debate"], ["market", "risk_debate"],
  ["news", "risk_debate"], ["sentiment", "risk_debate"],
  ["risk_debate", "risk_facilitator"], ["trader", "risk_facilitator"],
  ["risk_facilitator", "portfolio_manager"], ["risk_debate", "portfolio_manager"],
  ["trader", "portfolio_manager"], ["fundamentals", "portfolio_manager"],
  ["portfolio_manager", "decision_verifier"], ["market", "decision_verifier"],
  ["fundamentals", "decision_verifier"], ["news", "decision_verifier"],
  ["decision_verifier", "save_episode"], ["market", "save_episode"],
  ["save_episode", "memory", true],
];

export function stripHtml(s: string): string {
  return s.replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&").replace(/&nbsp;/g, " ").trim();
}
