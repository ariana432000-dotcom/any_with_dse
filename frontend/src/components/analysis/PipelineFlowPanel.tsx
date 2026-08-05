"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { GitBranch } from "lucide-react";
import type { PipelineStep } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Card, CardHeader } from "@/components/ui/Card";

/**
 * Static description of every stage the backend pipeline can run
 * (mirrors backend/app/pipeline/runner.py STAGES 1:1 — same ids).
 * Grouped into rows for the flow layout, plus a data-flow edge list so we
 * can draw connectors and highlight "where does this agent's data come
 * from / go to" when a node is selected.
 */
interface StageMeta {
  id: string;
  label: string;
  group: string;
  blurb: string;
}

const STAGE_META: StageMeta[] = [
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

// Row order mirrors the pipeline's actual data dependencies, not just
// STAGES list order. Two groups are intentionally *unordered* buckets:
//   - analysts: fundamentals/market/news/sentiment/macro_regime don't read
//     each other's output, so no sub-order is implied or should be.
//   - memory: retrieve_similar_episodes() and run_post_mortem() are both
//     independent reads that only feed into Trader — same reasoning.
// trader and save_episode each get their own row (not lumped into
// "decision" / "memory") because they're temporally far from the other
// members of those buckets — trader runs before Risk Debate, Portfolio
// Manager/Decision Verifier run after it, and save_episode is the very
// last stage of the run, not a mid-pipeline memory read.
const GROUPS: { id: string; label: string }[] = [
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
const EDGES: [string, string, boolean?][] = [
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

function stripHtml(s: string): string {
  return s.replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&").replace(/&nbsp;/g, " ").trim();
}

function ValueBlock({ value }: { value: Record<string, unknown> | string | undefined }) {
  if (value === undefined || value === null || value === "") {
    return <p className="text-xs text-text-faint">(empty)</p>;
  }
  if (typeof value === "string") {
    return (
      <pre className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-lg bg-bg-raised p-3 text-[11px] leading-relaxed text-text-muted">
        {stripHtml(value)}
      </pre>
    );
  }
  const entries = Object.entries(value);
  if (!entries.length) return <p className="text-xs text-text-faint">(empty)</p>;
  return (
    <div className="overflow-hidden rounded-lg border border-border-soft">
      {entries.map(([k, v]) => {
        const display = typeof v === "object" && v !== null ? JSON.stringify(v, null, 2) : String(v);
        return (
          <div key={k} className="flex gap-3 border-b border-border-soft px-3 py-2 text-xs last:border-b-0">
            <span className="w-2/5 shrink-0 text-text-faint">{k}</span>
            <span className="whitespace-pre-wrap text-text-muted">{stripHtml(display).slice(0, 1500)}</span>
          </div>
        );
      })}
    </div>
  );
}

export function PipelineFlowPanel({ pipeline }: { pipeline: PipelineStep[] | undefined }) {
  const steps = pipeline || [];
  const byStage = useMemo(() => {
    const m = new Map<string, PipelineStep>();
    steps.forEach((s) => m.set(s.stage, s));
    return m;
  }, [steps]);

  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<"input" | "output">("input");

  useEffect(() => {
    if (!selected) {
      const firstDone = STAGE_META.find((s) => byStage.has(s.id));
      if (firstDone) setSelected(firstDone.id);
    }
  }, [byStage, selected]);

  const nodeRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const [paths, setPaths] = useState<{ d: string; kind: "in" | "out" | "idle"; feedback?: boolean }[]>([]);

  useLayoutEffect(() => {
    function draw() {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const cRect = canvas.getBoundingClientRect();
      const next: { d: string; kind: "in" | "out" | "idle"; feedback?: boolean }[] = [];
      EDGES.forEach(([from, to, feedback]) => {
        const a = nodeRefs.current[from];
        const b = nodeRefs.current[to];
        if (!a || !b) return;
        const ar = a.getBoundingClientRect();
        const br = b.getBoundingClientRect();
        let d: string;
        if (feedback) {
          const x1 = ar.right - cRect.left, y1 = ar.top + ar.height / 2 - cRect.top;
          const x2 = br.right - cRect.left, y2 = br.top + br.height / 2 - cRect.top;
          const bulge = 46;
          d = `M ${x1} ${y1} C ${x1 + bulge} ${y1}, ${x2 + bulge} ${y2}, ${x2} ${y2}`;
        } else {
          const x1 = ar.left + ar.width / 2 - cRect.left, y1 = ar.bottom - cRect.top;
          const x2 = br.left + br.width / 2 - cRect.left, y2 = br.top - cRect.top;
          const dy = Math.max(24, (y2 - y1) / 2);
          d = `M ${x1} ${y1} C ${x1} ${y1 + dy}, ${x2} ${y2 - dy}, ${x2} ${y2}`;
        }
        let kind: "in" | "out" | "idle" = "idle";
        if (selected) {
          if (to === selected) kind = "in";
          else if (from === selected) kind = "out";
        }
        next.push({ d, kind, feedback });
      });
      setPaths(next);
    }
    draw();
    const ro = new ResizeObserver(draw);
    if (canvasRef.current) ro.observe(canvasRef.current);
    window.addEventListener("resize", draw);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", draw);
    };
  }, [selected, steps.length]);

  const selectedStep = selected ? byStage.get(selected) : undefined;
  const selectedMeta = selected ? STAGE_META.find((s) => s.id === selected) : undefined;
  const incoming = selected ? EDGES.filter((e) => e[1] === selected && !e[2]).map((e) => e[0]) : [];
  const outgoing = selected ? EDGES.filter((e) => e[0] === selected && !e[2]).map((e) => e[1]) : [];

  if (!steps.length) {
    return (
      <Card>
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              <GitBranch className="size-4 text-text-faint" />
              Agent pipeline flow
            </span>
          }
          subtitle="Once the analysis is complete, you'll see each agent's input/output here."
        />
        <p className="text-xs text-text-faint">Waiting for pipeline steps to be recorded…</p>
      </Card>
    );
  }

  return (
    <Card padded={false} className="overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-border-soft px-5 py-4">
        <div className="flex items-center gap-2">
          <GitBranch className="size-4 text-text-faint" />
          <h2 className="text-sm font-semibold text-text">Agent pipeline flow</h2>
        </div>
        <span className="text-xs text-text-faint">{steps.length} / {STAGE_META.length} stages recorded</span>
      </div>

      <div className="flex flex-col lg:flex-row">
        {/* -------- canvas: flow diagram -------- */}
        <div className="min-w-0 flex-1 overflow-x-auto p-5">
          <div ref={canvasRef} className="relative">
            <svg className="pointer-events-none absolute inset-0 h-full w-full overflow-visible">
              {paths.map((p, i) => (
                <path
                  key={i}
                  d={p.d}
                  fill="none"
                  strokeWidth={p.kind === "idle" ? 1 : 2}
                  strokeDasharray={p.feedback ? "4 4" : undefined}
                  className={cn(
                    p.kind === "idle" && "stroke-border-soft",
                    p.kind === "in" && "stroke-accent",
                    p.kind === "out" && "stroke-hold",
                  )}
                  opacity={p.kind === "idle" ? 0.5 : 0.95}
                />
              ))}
            </svg>

            <div className="relative flex flex-col gap-7">
              {GROUPS.map((group) => {
                const nodes = STAGE_META.filter((s) => s.group === group.id);
                if (!nodes.length) return null;
                return (
                  <div key={group.id}>
                    <p className="mb-2 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wide text-text-faint">
                      {group.label}
                      <span className="h-px flex-1 bg-border-soft" />
                    </p>
                    <div className="flex flex-wrap gap-3">
                      {nodes.map((n) => {
                        const done = byStage.has(n.id);
                        const isSelected = selected === n.id;
                        return (
                          <button
                            key={n.id}
                            ref={(el) => {
                              nodeRefs.current[n.id] = el;
                            }}
                            onClick={() => {
                              setSelected(n.id);
                              setTab("input");
                            }}
                            className={cn(
                              "w-[190px] rounded-lg border px-3 py-2.5 text-left transition-colors",
                              done ? "border-border bg-panel hover:border-accent/50" : "border-dashed border-border-soft bg-transparent opacity-50",
                              isSelected && "border-accent bg-accent-soft",
                            )}
                          >
                            <p className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-text-faint">
                              <span className={cn("size-1.5 rounded-full", done ? "bg-buy" : "bg-text-faint")} />
                              {done ? "recorded" : "not reached"}
                            </p>
                            <p className="text-xs font-semibold leading-tight text-text">{n.label}</p>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* -------- right side: selected agent detail -------- */}
        <div className="w-full shrink-0 border-t border-border-soft p-5 lg:w-[360px] lg:border-l lg:border-t-0">
          {!selectedMeta ? (
            <p className="text-xs text-text-faint">Click an agent to see details.</p>
          ) : (
            <div>
              <p className="mb-1 text-[10px] uppercase tracking-wide text-text-faint">
                {GROUPS.find((g) => g.id === selectedMeta.group)?.label}
              </p>
              <h3 className="text-sm font-semibold text-text">{selectedMeta.label}</h3>
              <p className="mt-1.5 text-xs leading-relaxed text-text-muted">{selectedMeta.blurb}</p>

              {selectedStep ? (
                <>
                  <div className="mt-4 flex gap-1 rounded-lg border border-border-soft bg-bg-raised p-1">
                    <button
                      onClick={() => setTab("input")}
                      className={cn(
                        "flex-1 rounded-md py-1.5 text-xs font-medium transition-colors",
                        tab === "input" ? "bg-panel text-text shadow-sm" : "text-text-faint hover:text-text-muted",
                      )}
                    >
                      Input
                    </button>
                    <button
                      onClick={() => setTab("output")}
                      className={cn(
                        "flex-1 rounded-md py-1.5 text-xs font-medium transition-colors",
                        tab === "output" ? "bg-panel text-text shadow-sm" : "text-text-faint hover:text-text-muted",
                      )}
                    >
                      Output
                    </button>
                  </div>

                  <div className="mt-3">
                    <ValueBlock value={tab === "input" ? selectedStep.input : selectedStep.output} />
                  </div>

                  {selectedStep.latency_ms ? (
                    <p className="mt-3 text-[10px] text-text-faint">
                      latency {(selectedStep.latency_ms / 1000).toFixed(1)}s
                    </p>
                  ) : null}
                </>
              ) : (
                <p className="mt-4 text-xs text-text-faint">
                  This step hasn't run yet — its input/output will appear here once it does.
                </p>
              )}

              {incoming.length ? (
                <>
                  <p className="mb-1.5 mt-4 text-[10px] uppercase tracking-wide text-text-faint">Data comes from</p>
                  <div className="flex flex-wrap gap-1.5">
                    {incoming.map((id) => (
                      <button
                        key={id}
                        onClick={() => {
                          setSelected(id);
                          setTab("input");
                        }}
                        className="rounded-full border border-border-soft bg-bg-raised px-2.5 py-1 text-[11px] text-text-muted hover:border-accent/50 hover:text-text"
                      >
                        {STAGE_META.find((s) => s.id === id)?.label ?? id}
                      </button>
                    ))}
                  </div>
                </>
              ) : null}

              {outgoing.length ? (
                <>
                  <p className="mb-1.5 mt-3 text-[10px] uppercase tracking-wide text-text-faint">Data goes to</p>
                  <div className="flex flex-wrap gap-1.5">
                    {outgoing.map((id) => (
                      <button
                        key={id}
                        onClick={() => {
                          setSelected(id);
                          setTab("input");
                        }}
                        className="rounded-full border border-border-soft bg-bg-raised px-2.5 py-1 text-[11px] text-text-muted hover:border-accent/50 hover:text-text"
                      >
                        {STAGE_META.find((s) => s.id === id)?.label ?? id}
                      </button>
                    ))}
                  </div>
                </>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
