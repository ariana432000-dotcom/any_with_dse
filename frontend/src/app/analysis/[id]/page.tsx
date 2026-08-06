"use client";

import { use, useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { ArrowLeft, Clock, Cpu, RefreshCw } from "lucide-react";
import { analysisApi, ApiError } from "@/lib/api";
import { useAnalysis } from "@/hooks/useAnalysis";
import { useAnalysisSocket } from "@/hooks/useAnalysisSocket";
import { AGENT_LABELS } from "@/lib/constants";
import { formatDateTime } from "@/lib/utils";
import { Badge, SignalBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { AgentCard } from "@/components/analysis/AgentCard";
import { PipelineFlowPanel } from "@/components/analysis/PipelineFlowPanel";
import { RecommendationPanel } from "@/components/analysis/RecommendationPanel";
import { StageTabs } from "@/components/analysis/StageTabs";
import { AnalysisProgress } from "@/components/analysis/AnalysisProgress";

const ACTIVE_STATUSES = new Set(["PENDING", "RUNNING"]);

export default function AnalysisDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { analysis, loading, error, refresh } = useAnalysis(id);
  const isActive = analysis ? ACTIVE_STATUSES.has(analysis.status) : true;
  const { events, status: wsStatus } = useAnalysisSocket(id, isActive);
  const [showTrace, setShowTrace] = useState(false);

  if (loading && !analysis) return <LoadingState label="Loading analysis…" />;
  if (error && !analysis) {
    return <ErrorState title="Couldn't load this analysis" description={error} onRetry={refresh} />;
  }
  if (!analysis) return null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link href="/analysis" className="mb-2 inline-flex items-center gap-1 text-xs text-text-muted hover:text-text">
            <ArrowLeft className="size-3.5" />
            Back to analyses
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="font-mono text-2xl font-bold tracking-wide text-text">{analysis.ticker}</h1>
            <SignalBadge signal={analysis.recommendation?.signal} />
            <Badge tone={analysis.status === "COMPLETED" ? "buy" : analysis.status === "FAILED" ? "sell" : "hold"}>
              {analysis.status}
            </Badge>
          </div>
          <p className="mt-1 text-xs text-text-faint">
            Started {formatDateTime(analysis.metadata.started_at || analysis.created_at)}
            {analysis.metadata.finished_at ? ` · finished ${formatDateTime(analysis.metadata.finished_at)}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={refresh}>
            <RefreshCw className="size-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {analysis.error ? (
        <ErrorState title="Analysis failed" description={analysis.error} />
      ) : null}

      {isActive ? <AnalysisProgress events={events} status={wsStatus} /> : null}

      <PipelineFlowPanel pipeline={analysis.pipeline} />

      <RecommendationPanel recommendation={analysis.recommendation} />

      <div>
        <h2 className="mb-3 text-sm font-semibold text-text">Agent analyses — at a glance</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <AgentCard label={AGENT_LABELS.technical} agent={analysis.technical} />
          <AgentCard label={AGENT_LABELS.fundamental} agent={analysis.fundamental} />
          <AgentCard label={AGENT_LABELS.news} agent={analysis.news} />
          <AgentCard label={AGENT_LABELS.sentiment} agent={analysis.sentiment} />
        </div>
      </div>

      <StageTabs analysis={analysis} />

      <div className="rounded-xl border border-border-soft bg-panel p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-text">
            <Cpu className="size-4 text-text-faint" />
            Execution metadata
          </h2>
          <button
            onClick={() => setShowTrace((v) => !v)}
            className="text-xs font-medium text-accent hover:text-accent-strong"
          >
            {showTrace ? "Hide" : "Show"} raw trace
          </button>
        </div>
        <div className="grid grid-cols-2 gap-4 text-xs sm:grid-cols-4">
          <MetaField label="Provider" value={analysis.metadata.provider || "—"} />
          <MetaField
            label="Total latency"
            value={
              analysis.metadata.total_latency_ms
                ? `${(analysis.metadata.total_latency_ms / 1000).toFixed(1)}s`
                : "—"
            }
            icon={<Clock className="size-3" />}
          />
          <MetaField label="Agents run" value={String(analysis.metadata.agent_count)} />
          <MetaField label="Memory hits" value={String(analysis.metadata.memory_hits)} />
        </div>
        {analysis.metadata.failed_agents.length > 0 ? (
          <p className="mt-3 text-xs text-sell">
            Failed agents: {analysis.metadata.failed_agents.join(", ")}
          </p>
        ) : null}
        {showTrace ? <TraceViewer analysisId={id} /> : null}
      </div>
    </div>
  );
}

function MetaField({ label, value, icon }: { label: string; value: string; icon?: ReactNode }) {
  return (
    <div>
      <p className="mb-1 flex items-center gap-1 text-[10px] uppercase tracking-wide text-text-faint">
        {icon}
        {label}
      </p>
      <p className="font-mono text-text">{value}</p>
    </div>
  );
}

function TraceViewer({ analysisId }: { analysisId: string }) {
  const [trace, setTrace] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    analysisApi
      .getTrace(analysisId)
      .then((data) => {
        if (!cancelled) setTrace(data);
      })
      .catch((e) => {
        if (!cancelled) setErr(e instanceof ApiError ? e.message : "No trace available");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [analysisId]);

  return (
    <div className="mt-4 border-t border-border-soft pt-4">
      {loading ? (
        <p className="text-xs text-text-faint">Loading trace…</p>
      ) : err ? (
        <p className="text-xs text-text-faint">{err}</p>
      ) : (
        <pre className="max-h-80 overflow-auto rounded-lg bg-bg-raised p-3 text-[11px] leading-relaxed text-text-muted">
          {JSON.stringify(trace, null, 2)}
        </pre>
      )}
    </div>
  );
}
