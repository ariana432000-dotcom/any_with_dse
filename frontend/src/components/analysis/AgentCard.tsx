import type { AgentView } from "@/lib/types";
import { Card } from "@/components/ui/Card";
import { SignalBadge } from "@/components/ui/Badge";
import { Badge } from "@/components/ui/Badge";
import { AlertCircle } from "lucide-react";

export function AgentCard({ label, agent }: { label: string; agent: AgentView | null }) {
  if (!agent) {
    return (
      <Card className="flex flex-col items-center justify-center gap-2 text-center">
        <div className="size-[72px] rounded-full border-2 border-dashed border-border" />
        <p className="text-xs text-text-faint">{label} — not run yet</p>
      </Card>
    );
  }

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">{label}</p>
          {!agent.ok ? (
            <Badge tone="sell" className="mt-1.5">
              <AlertCircle className="size-3" />
              Failed
            </Badge>
          ) : (
            <p className="mt-1 font-mono text-[11px] text-text-faint">
              {agent.latency_ms > 0 ? `${Math.round(agent.latency_ms)}ms` : ""}
            </p>
          )}
        </div>
        <div className="text-right">
          <SignalBadge signal={agent.signal} />
          <p className="mt-1 font-mono text-[11px] text-text-faint">
            {Math.round(Math.min(1, Math.max(0, agent.confidence)) * 100)}%
          </p>
        </div>
      </div>
      <p className="mt-3 line-clamp-4 text-xs leading-relaxed text-text-muted">
        {agent.error || agent.analysis || "No analysis text returned."}
      </p>
    </Card>
  );
}
