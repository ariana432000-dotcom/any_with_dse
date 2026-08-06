import type { PostMortemState } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/States";
import { History } from "lucide-react";

export function PostMortemPanel({ postMortem }: { postMortem: PostMortemState | null }) {
  if (!postMortem || postMortem.episodes_reviewed === 0) {
    return (
      <Card>
        <CardHeader
          title="Post-Mortem Review"
          subtitle="Cross-regime self-critique over this ticker's resolved track record."
        />
        <EmptyState
          icon={<History className="size-5" />}
          title="No resolved episodes yet"
          description="Once past decisions on this ticker resolve to a P&L outcome, they'll be reviewed here every run."
        />
      </Card>
    );
  }

  const lines = postMortem.lessons.split("\n").map((l) => l.trim()).filter(Boolean);
  const bullets = lines.filter((l) => l.startsWith("-") || l.startsWith("•"));
  const isBulleted = bullets.length > 0 && bullets.length === lines.length;

  return (
    <Card>
      <CardHeader
        title="Post-Mortem Review"
        subtitle={`${postMortem.episodes_reviewed} resolved episode(s) reviewed, across every regime.`}
      />
      {isBulleted ? (
        <ul className="space-y-2">
          {lines.map((line, i) => (
            <li key={i} className="flex gap-2 text-xs leading-relaxed text-text-muted">
              <span className="mt-0.5 text-text-faint">•</span>
              <span>{line.replace(/^[-•]\s*/, "")}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="whitespace-pre-line text-xs leading-relaxed text-text-muted">{postMortem.lessons}</p>
      )}
    </Card>
  );
}
