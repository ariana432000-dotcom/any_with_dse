import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Card } from "./Card";

export function StatCard({
  label,
  value,
  hint,
  icon,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  tone?: "neutral" | "buy" | "sell" | "hold" | "accent";
}) {
  const toneClass = {
    neutral: "text-text",
    buy: "text-buy",
    sell: "text-sell",
    hold: "text-hold",
    accent: "text-accent-strong",
  }[tone];

  return (
    <Card className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <p className="text-xs font-medium uppercase tracking-wider text-text-muted">{label}</p>
        <p className={cn("mt-2 font-mono text-2xl font-semibold tabular-nums", toneClass)}>{value}</p>
        {hint ? <p className="mt-1 truncate text-xs text-text-faint">{hint}</p> : null}
      </div>
      {icon ? (
        <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-bg-raised text-text-muted">
          {icon}
        </div>
      ) : null}
    </Card>
  );
}
