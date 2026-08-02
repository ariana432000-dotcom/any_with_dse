import type { MemoryState } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/States";
import { formatDate } from "@/lib/utils";
import { Brain } from "lucide-react";

export function AnalysisMemoryPanel({ memory }: { memory: MemoryState | null }) {
  if (!memory || memory.hits.length === 0) {
    return (
      <Card>
        <CardHeader title="RAEM Memory" subtitle="Episodic memory retrieved for this run." />
        <EmptyState icon={<Brain className="size-5" />} title="No similar past episodes retrieved" />
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="RAEM Memory"
        subtitle={`${memory.episodic_count} episode(s) · regime: ${memory.regime || "unknown"}`}
      />
      <ul className="space-y-2">
        {memory.hits.map((hit, i) => (
          <li
            key={hit.memory_id || i}
            className="flex items-center justify-between gap-3 rounded-lg border border-border-soft bg-bg-raised px-3 py-2"
          >
            <div className="min-w-0">
              <p className="truncate text-xs font-medium text-text">
                {hit.ticker} · {formatDate(hit.timestamp)}
              </p>
              <p className="truncate text-[11px] text-text-faint">{hit.decision || "no decision recorded"}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {hit.similarity !== null ? (
                <span className="font-mono text-[11px] text-text-muted">
                  {Math.round(hit.similarity * 100)}%
                </span>
              ) : null}
              <Badge tone={hit.outcome === "WIN" ? "buy" : hit.outcome === "LOSS" ? "sell" : "neutral"}>
                {hit.outcome || "PENDING"}
              </Badge>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
