import type { DebateState } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/States";
import { cn } from "@/lib/utils";
import { Swords } from "lucide-react";

const SIDE_STYLES: Record<string, string> = {
  bull: "border-buy/30 bg-buy-soft",
  bear: "border-sell/30 bg-sell-soft",
  aggressive: "border-sell/30 bg-sell-soft",
  conservative: "border-accent/30 bg-accent-soft",
  neutral: "border-border bg-bg-raised",
};

export function DebatePanel({ debate }: { debate: DebateState | null }) {
  if (!debate || debate.turns.length === 0) {
    return (
      <Card>
        <CardHeader title="AI Debate" subtitle="Bull vs. bear investment debate, then risk debate." />
        <EmptyState icon={<Swords className="size-5" />} title="No debate recorded for this run" />
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="AI Debate"
        subtitle={debate.winner ? `Winning side: ${debate.winner}` : "Bull vs. bear investment debate."}
      />
      <ol className="space-y-3">
        {debate.turns.map((turn, i) => (
          <li
            key={i}
            className={cn(
              "rounded-lg border p-3",
              SIDE_STYLES[turn.side.toLowerCase()] ?? SIDE_STYLES.neutral,
            )}
          >
            <div className="mb-1.5 flex items-center gap-2">
              <span className="text-xs font-semibold text-text">{turn.speaker}</span>
              {turn.side ? (
                <Badge tone={turn.side.toLowerCase() === "bull" ? "buy" : turn.side.toLowerCase() === "bear" ? "sell" : "neutral"}>
                  {turn.side}
                </Badge>
              ) : null}
              {turn.round ? <span className="text-[10px] text-text-faint">round {turn.round}</span> : null}
            </div>
            <p className="text-xs leading-relaxed text-text-muted">{turn.content}</p>
          </li>
        ))}
      </ol>
      {debate.summary ? (
        <div className="mt-4 rounded-lg border border-border-soft bg-bg-raised p-3">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-text-faint">Summary</p>
          <p className="text-xs leading-relaxed text-text-muted">{debate.summary}</p>
        </div>
      ) : null}
    </Card>
  );
}
