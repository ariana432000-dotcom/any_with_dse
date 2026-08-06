"use client";

import Link from "next/link";
import { Activity, Brain, Database, Radio, Server, TrendingUp } from "lucide-react";
import { useHealth } from "@/hooks/useHealth";
import { useWatchlist } from "@/hooks/useWatchlist";
import { useLiveFeed } from "@/hooks/useLiveFeed";
import { Card, CardHeader } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { Badge } from "@/components/ui/Badge";
import { WatchlistTable } from "@/components/market/WatchlistTable";
import { AnalysisForm } from "@/components/analysis/AnalysisForm";
import { EmptyState, Skeleton } from "@/components/ui/States";
import { cn, timeAgo } from "@/lib/utils";

const STAGE_LABELS: Record<string, string> = {
  STARTED: "started",
  FETCHING_MARKET_DATA: "fetching market data",
  RETRIEVING_MEMORY: "retrieving memory",
  RUNNING_TECHNICAL_AGENT: "technical analyst running",
  RUNNING_FUNDAMENTAL_AGENT: "fundamentals analyst running",
  RUNNING_NEWS_AGENT: "news analyst running",
  RUNNING_SENTIMENT_AGENT: "sentiment analyst running",
  RUNNING_DEBATE: "debating",
  RUNNING_RISK_MANAGER: "assessing risk",
  RUNNING_PORTFOLIO_MANAGER: "portfolio manager deciding",
  GENERATING_RECOMMENDATION: "generating recommendation",
  SAVING_RESULTS: "saving results",
  COMPLETED: "completed",
  ERROR: "errored",
};

export default function DashboardPage() {
  const { health, loading: healthLoading } = useHealth();
  const { tickers } = useWatchlist();
  const { events, status } = useLiveFeed(12);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-xl font-semibold text-text">Dashboard</h1>
        <p className="mt-1 text-sm text-text-muted">
          Local AI trading research — TradingAgents + RAEM, running on your own machine.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          label="Backend"
          value={healthLoading ? <Skeleton className="h-7 w-16" /> : health?.status === "ok" ? "Online" : "Degraded"}
          tone={health?.status === "ok" ? "buy" : "hold"}
          icon={<Server className="size-4" />}
          hint={healthLoading ? undefined : health ? `mongo · redis · chroma` : "unreachable"}
        />
        <StatCard
          label="AI Engine"
          value={healthLoading ? <Skeleton className="h-7 w-16" /> : health?.ai_provider ?? "—"}
          tone={health?.ai_configured ? "accent" : "hold"}
          icon={<Brain className="size-4" />}
          hint={health?.ai_model}
        />
        <StatCard
          label="Memory"
          value={
            healthLoading ? (
              <Skeleton className="h-7 w-16" />
            ) : health?.services.chroma.ok ? (
              "Ready"
            ) : (
              "Unavailable"
            )
          }
          tone={health?.services.chroma.ok ? "buy" : "sell"}
          icon={<Database className="size-4" />}
          hint="ChromaDB / RAEM"
        />
        <StatCard
          label="Live feed"
          value={status === "open" ? "Connected" : "Connecting…"}
          tone={status === "open" ? "buy" : "hold"}
          icon={<Radio className="size-4" />}
          hint={`${tickers.length} tickers watched`}
        />
      </div>

      <AnalysisForm />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Watchlist"
            subtitle="Live quotes for your saved tickers."
            action={
              <Link href="/watchlist" className="text-xs font-medium text-accent hover:text-accent-strong">
                Manage →
              </Link>
            }
          />
          <WatchlistTable tickers={tickers.slice(0, 6)} />
        </Card>

        <Card>
          <CardHeader
            title="Live activity"
            subtitle="Every running analysis, in real time."
            action={
              <span className="flex items-center gap-1.5 text-[11px] text-text-faint">
                <span className={cn("size-1.5 rounded-full", status === "open" ? "bg-buy animate-pulse-dot" : "bg-hold")} />
                {status === "open" ? "live" : "connecting"}
              </span>
            }
          />
          {events.length === 0 ? (
            <EmptyState
              icon={<Activity className="size-5" />}
              title="No activity yet"
              description="Run an analysis to see live pipeline events here."
            />
          ) : (
            <ul className="space-y-2.5">
              {events.map((evt, i) => (
                <li key={i} className="flex items-start gap-2 text-xs">
                  <TrendingUp className="mt-0.5 size-3.5 shrink-0 text-text-faint" />
                  <div className="min-w-0">
                    <p className="text-text">
                      <span className="font-mono font-medium">{evt.ticker || "—"}</span>{" "}
                      <span className="text-text-muted">
                        {STAGE_LABELS[evt.type as string] ?? String(evt.type).toLowerCase()}
                      </span>
                    </p>
                    <p className="text-text-faint">{timeAgo(evt.ts)}</p>
                  </div>
                  {evt.analysis_id ? (
                    <Link
                      href={`/analysis/${evt.analysis_id}`}
                      className="ml-auto shrink-0 text-[10px] text-accent hover:text-accent-strong"
                    >
                      view
                    </Link>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {!health?.ai_configured && !healthLoading ? (
        <Card className="border-hold/30 bg-hold-soft">
          <div className="flex items-center gap-2">
            <Badge tone="hold">Setup needed</Badge>
            <p className="text-xs text-text-muted">
              No AI provider is configured — pull a local model with Ollama and set{" "}
              <code className="rounded bg-bg-raised px-1 py-0.5 font-mono">RAEM_LLM_PROVIDER=ollama</code>{" "}
              in your backend <code className="rounded bg-bg-raised px-1 py-0.5 font-mono">.env</code>.
            </p>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
