import type { MemoryCollection } from "./types";

export const APP_NAME = "AInvest";

export const DEFAULT_WATCHLIST = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN"];

export const WATCHLIST_STORAGE_KEY = "ainvest:watchlist";
export const THEME_STORAGE_KEY = "ainvest:theme";

export interface NavItem {
  href: string;
  label: string;
  icon:
    | "dashboard"
    | "analysis"
    | "watchlist"
    | "news"
    | "memory"
    | "dataset"
    | "backtest"
    | "paper-trading"
    | "settings";
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Dashboard", icon: "dashboard" },
  { href: "/analysis", label: "AI Analysis", icon: "analysis" },
  { href: "/watchlist", label: "Watchlist", icon: "watchlist" },
  { href: "/paper-trading", label: "Paper Trading", icon: "paper-trading" },
  { href: "/backtest", label: "Backtest", icon: "backtest" },
  { href: "/dataset", label: "Dataset Explorer", icon: "dataset" },
  { href: "/news", label: "News", icon: "news" },
  { href: "/memory", label: "Memory", icon: "memory" },
  { href: "/settings", label: "Settings", icon: "settings" },
];

export const MEMORY_COLLECTION_LABELS: Record<MemoryCollection, string> = {
  episodic_memory: "Episodic Memory",
  market_memory: "Market Memory",
  conversation_memory: "Conversations",
  portfolio_memory: "Portfolio Memory",
  research_memory: "Research Memory",
  news_memory: "News Memory",
  execution_history: "Execution History",
  agent_reasoning: "Agent Reasoning",
};

export const MEMORY_COLLECTION_DESCRIPTIONS: Record<MemoryCollection, string> = {
  episodic_memory: "Past trade episodes RAEM retrieves for similar future setups.",
  market_memory: "Regime-tagged market snapshots used for context injection.",
  conversation_memory: "AI chat / conversational turns kept for continuity.",
  portfolio_memory: "Portfolio-manager decisions and allocation history.",
  research_memory: "Fundamental & research notes gathered by analyst agents.",
  news_memory: "Embedded news chunks used for retrieval-augmented sentiment.",
  execution_history: "A trace of full pipeline executions.",
  agent_reasoning: "Raw per-agent reasoning captured for post-mortems.",
};

export const AGENT_LABELS: Record<string, string> = {
  technical: "Technical Analyst",
  fundamental: "Fundamentals Analyst",
  news: "News Analyst",
  sentiment: "Sentiment Analyst",
};
