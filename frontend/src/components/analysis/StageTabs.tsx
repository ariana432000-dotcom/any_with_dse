"use client";

import { useMemo, useState } from "react";
import type { AnalysisResponse, AgentView, PipelineStep } from "@/lib/types";
import { STAGE_META, STAGE_GROUPS } from "@/lib/pipelineStages";
import { Card, CardHeader } from "@/components/ui/Card";
import { Tabs } from "@/components/ui/Tabs";
import { Badge, SignalBadge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/States";
import { ValueBlock } from "@/components/analysis/PipelineFlowPanel";
import { DebatePanel } from "@/components/analysis/DebatePanel";
import { MacroRegimePanel } from "@/components/analysis/MacroRegimePanel";
import { AnalysisMemoryPanel } from "@/components/analysis/AnalysisMemoryPanel";
import { PostMortemPanel } from "@/components/analysis/PostMortemPanel";
import { VerifierPanel } from "@/components/analysis/VerifierPanel";
import { formatCurrency } from "@/lib/utils";
import { AlertCircle, Inbox } from "lucide-react";

/** Full (non-truncated) view of one analyst's signal + reasoning -- used
 * for the dedicated Fundamentals/Market/News/Sentiment tabs. AgentCard
 * (the compact grid overview elsewhere on the page) line-clamps to 4
 * lines on purpose; a dedicated tab has room to show everything. */
function AgentFullView({ label, agent }: { label: string; agent: AgentView | null }) {
  if (!agent) {
    return <EmptyState icon={<Inbox className="size-5" />} title={`${label} — not run yet`} />;
  }
  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <SignalBadge signal={agent.signal} />
        <span className="font-mono text-xs text-text-faint">
          confidence {Math.round(Math.min(1, Math.max(0, agent.confidence)) * 100)}%
        </span>
        {!agent.ok ? (
          <Badge tone="sell">
            <AlertCircle className="size-3" />
            Failed
          </Badge>
        ) : null}
        {agent.latency_ms > 0 ? (
          <span className="font-mono text-[11px] text-text-faint">{Math.round(agent.latency_ms)}ms</span>
        ) : null}
      </div>
      <p className="whitespace-pre-line text-xs leading-relaxed text-text-muted">
        {agent.error || agent.analysis || "No analysis text returned."}
      </p>
    </div>
  );
}

/** Fallback for stages with no dedicated structured state (Outcome
 * Backfill, Trader Proposal, Save Episode, and Investment Facilitator's
 * raw form) -- shows the raw pipeline-step input/output, same rendering
 * PipelineFlowPanel already uses for its side-panel detail view. */
function RawStageView({ step }: { step: PipelineStep | undefined }) {
  const [tab, setTab] = useState<"input" | "output">("output");
  if (!step) {
    return <EmptyState icon={<Inbox className="size-5" />} title="This stage hasn't run yet" />;
  }
  return (
    <div>
      <div className="mb-3 flex gap-1 rounded-lg border border-border-soft bg-bg-raised p-1">
        <button
          onClick={() => setTab("input")}
          className={`flex-1 rounded-md py-1.5 text-xs font-medium transition-colors ${
            tab === "input" ? "bg-panel text-text shadow-sm" : "text-text-faint hover:text-text-muted"
          }`}
        >
          Input
        </button>
        <button
          onClick={() => setTab("output")}
          className={`flex-1 rounded-md py-1.5 text-xs font-medium transition-colors ${
            tab === "output" ? "bg-panel text-text shadow-sm" : "text-text-faint hover:text-text-muted"
          }`}
        >
          Output
        </button>
      </div>
      <ValueBlock value={tab === "input" ? step.input : step.output} />
      {step.latency_ms ? (
        <p className="mt-3 text-[10px] text-text-faint">latency {(step.latency_ms / 1000).toFixed(1)}s</p>
      ) : null}
    </div>
  );
}

export function StageTabs({ analysis }: { analysis: AnalysisResponse }) {
  const pipeline = analysis.pipeline || [];
  const byStage = useMemo(() => {
    const m = new Map<string, PipelineStep>();
    pipeline.forEach((s) => m.set(s.stage, s));
    return m;
  }, [pipeline]);

  const [active, setActive] = useState<string>(
    STAGE_META.find((s) => byStage.has(s.id))?.id ?? STAGE_META[0].id,
  );

  const activeMeta = STAGE_META.find((s) => s.id === active)!;
  // These stages render an already-self-contained Card (own header/empty
  // states) -- shown as-is, no extra wrapper. Everything else gets a
  // lightweight inline header + this component's own Card frame.
  const selfContained = new Set([
    "macro_regime", "investment_debate", "risk_debate", "memory", "post_mortem", "decision_verifier",
  ]);

  return (
    <div>
      <Card padded={false} className="overflow-hidden">
        <div className="px-5 py-4">
          <h2 className="mb-3 text-sm font-semibold text-text">Agent stages</h2>
          <div className="space-y-2.5">
            {STAGE_GROUPS.map((group) => {
              const stages = STAGE_META.filter((s) => s.group === group.id);
              if (!stages.length) return null;
              return (
                <div key={group.id}>
                  <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-text-faint">
                    {group.label}
                  </p>
                  <Tabs
                    items={stages.map((s) => ({ id: s.id, label: s.label, done: byStage.has(s.id) }))}
                    active={active}
                    onChange={setActive}
                  />
                </div>
              );
            })}
          </div>
        </div>
      </Card>

      <div className="mt-4">
        {selfContained.has(active) ? (
          renderStageContent(active, analysis, byStage)
        ) : (
          <Card>
            <CardHeader title={activeMeta.label} subtitle={activeMeta.blurb} />
            {renderStageContent(active, analysis, byStage)}
          </Card>
        )}
      </div>
    </div>
  );
}

function renderStageContent(
  stage: string,
  a: AnalysisResponse,
  byStage: Map<string, PipelineStep>,
) {
  switch (stage) {
    case "fundamentals":
      return <AgentFullView label="Fundamentals Analyst" agent={a.fundamental} />;
    case "market":
      return <AgentFullView label="Market Analyst" agent={a.technical} />;
    case "news":
      return <AgentFullView label="News Analyst" agent={a.news} />;
    case "sentiment":
      return <AgentFullView label="Sentiment Analyst" agent={a.sentiment} />;
    case "macro_regime":
      return <MacroRegimePanel macro={a.macro} />;
    case "investment_debate":
      return (
        <DebatePanel
          debate={a.debate}
          sides={["bull", "bear"]}
          title=""
          emptyDescription="Bull and Bear analysts haven't debated yet."
        />
      );
    case "investment_facilitator":
      return a.debate?.summary ? (
        <div>
          {a.debate.winner ? (
            <Badge tone={a.debate.winner.toUpperCase().includes("BULL") ? "buy" : a.debate.winner.toUpperCase().includes("BEAR") ? "sell" : "neutral"} className="mb-3">
              {a.debate.winner}
            </Badge>
          ) : null}
          <p className="whitespace-pre-line text-xs leading-relaxed text-text-muted">{a.debate.summary}</p>
        </div>
      ) : (
        <RawStageView step={byStage.get("investment_facilitator")} />
      );
    case "memory":
      return <AnalysisMemoryPanel memory={a.memory} />;
    case "post_mortem":
      return <PostMortemPanel postMortem={a.post_mortem} />;
    case "risk_debate":
      return (
        <DebatePanel
          debate={a.debate}
          sides={["aggressive", "conservative", "neutral"]}
          title=""
          emptyDescription="Aggressive / Conservative / Neutral analysts haven't debated yet."
        />
      );
    case "risk_facilitator":
      return a.risk ? (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <span
              className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                a.risk.rating === "HIGH"
                  ? "border-sell/30 bg-sell-soft text-sell"
                  : a.risk.rating === "LOW"
                    ? "border-buy/30 bg-buy-soft text-buy"
                    : "border-hold/30 bg-hold-soft text-hold"
              }`}
            >
              {a.risk.rating || "N/A"} risk
            </span>
            {a.risk.position_sizing ? (
              <span className="text-xs text-text-muted">Position sizing: {a.risk.position_sizing}</span>
            ) : null}
          </div>
          <div className="flex gap-4 font-mono text-xs">
            <span className="text-text-faint">
              Stop-loss{" "}
              <span className="text-sell">
                {formatCurrency(a.risk.stop_loss, { currency: a.recommendation?.currency === "BDT" ? "BDT" : "USD" })}
              </span>
            </span>
            <span className="text-text-faint">
              Take-profit{" "}
              <span className="text-buy">
                {formatCurrency(a.risk.take_profit, { currency: a.recommendation?.currency === "BDT" ? "BDT" : "USD" })}
              </span>
            </span>
          </div>
          {a.risk.summary ? (
            <p className="whitespace-pre-line text-xs leading-relaxed text-text-muted">{a.risk.summary}</p>
          ) : null}
        </div>
      ) : (
        <RawStageView step={byStage.get("risk_facilitator")} />
      );
    case "portfolio_manager":
      return a.portfolio ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <SignalBadge signal={a.portfolio.signal} />
            {a.portfolio.allocation_pct !== null ? (
              <span className="font-mono text-xs text-text-muted">
                {a.portfolio.allocation_pct}% allocation
              </span>
            ) : null}
          </div>
          {a.portfolio.rationale ? (
            <p className="whitespace-pre-line text-xs leading-relaxed text-text-muted">
              {a.portfolio.rationale}
            </p>
          ) : null}
        </div>
      ) : (
        <RawStageView step={byStage.get("portfolio_manager")} />
      );
    case "decision_verifier":
      return <VerifierPanel verifier={a.verifier} />;
    case "outcome_backfill":
    case "trader":
    case "save_episode":
    default:
      return <RawStageView step={byStage.get(stage)} />;
  }
}
