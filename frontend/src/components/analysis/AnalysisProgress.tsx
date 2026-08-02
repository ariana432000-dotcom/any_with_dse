import type { ExecutionEventPayload } from "@/lib/types";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import type { ConnStatus } from "@/lib/ws";

const STAGE_LABELS: Record<string, string> = {
  STARTED: "Started",
  VALIDATING: "Validating request",
  FETCHING_MARKET_DATA: "Fetching market data",
  RETRIEVING_MEMORY: "Retrieving RAEM memory",
  RUNNING_TECHNICAL_AGENT: "Technical analyst",
  RUNNING_FUNDAMENTAL_AGENT: "Fundamentals analyst",
  RUNNING_NEWS_AGENT: "News analyst",
  RUNNING_MACRO_AGENT: "Macro regime analyst",
  RUNNING_SENTIMENT_AGENT: "Sentiment analyst",
  RUNNING_DEBATE: "Bull vs. bear debate",
  RUNNING_POST_MORTEM_AGENT: "Post-mortem review",
  RUNNING_RISK_MANAGER: "Risk manager",
  RUNNING_PORTFOLIO_MANAGER: "Portfolio manager",
  RUNNING_VERIFIER_AGENT: "Decision verifier",
  RUNNING_CIO: "Finalizing recommendation",
  GENERATING_RECOMMENDATION: "Generating recommendation",
  SAVING_RESULTS: "Saving results",
  AGENT_MESSAGE: "Agent message",
  COMPLETED: "Completed",
  ERROR: "Error",
};

export function AnalysisProgress({
  events,
  status,
}: {
  events: ExecutionEventPayload[];
  status: ConnStatus;
}) {
  const latest = [...events].reverse().find((e) => typeof e.progress === "number" && e.progress > 0);
  const progressPct = Math.round((latest?.progress ?? 0) * 100);
  const latestMessage = events[events.length - 1];
  const errored = events.some((e) => e.type === "ERROR");

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "size-2 rounded-full",
              errored ? "bg-sell" : status === "open" ? "bg-buy animate-pulse-dot" : "bg-hold animate-pulse-dot",
            )}
          />
          <p className="text-sm font-medium text-text">
            {errored ? "Execution failed" : "Analysis in progress"}
          </p>
        </div>
        <span className="font-mono text-xs text-text-muted">{progressPct}%</span>
      </div>

      <div className="mb-4 h-1.5 w-full overflow-hidden rounded-full bg-bg-raised">
        <div
          className={cn("h-full rounded-full transition-all duration-500", errored ? "bg-sell" : "bg-accent")}
          style={{ width: `${progressPct}%` }}
        />
      </div>

      {latestMessage ? (
        <p className="mb-4 text-xs text-text-muted">
          <span className="font-medium text-text">
            {STAGE_LABELS[latestMessage.type] ?? latestMessage.type}
          </span>
          {latestMessage.message ? ` — ${latestMessage.message}` : ""}
        </p>
      ) : (
        <p className="mb-4 text-xs text-text-faint">Waiting for the backend to start streaming events…</p>
      )}

      <ol className="max-h-56 space-y-1.5 overflow-y-auto pr-1">
        {events
          .filter((e) => e.type !== "SUBSCRIBED" && e.type !== "SNAPSHOT")
          .map((evt, i) => (
            <li key={i} className="flex items-center gap-2 text-[11px] text-text-faint">
              <span className="font-mono">{evt.ts ? new Date(evt.ts).toLocaleTimeString() : ""}</span>
              <span className="text-text-muted">{STAGE_LABELS[evt.type] ?? evt.type}</span>
            </li>
          ))}
      </ol>
    </Card>
  );
}
