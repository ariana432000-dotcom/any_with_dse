import type { RecommendationState } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { SignalGauge } from "@/components/ui/SignalGauge";
import { SignalBadge } from "@/components/ui/Badge";
import { formatCurrency } from "@/lib/utils";
import { EmptyState } from "@/components/ui/States";
import { Target } from "lucide-react";

export function RecommendationPanel({ recommendation }: { recommendation: RecommendationState | null }) {
  if (!recommendation) {
    return (
      <Card>
        <CardHeader title="Recommendation" />
        <EmptyState icon={<Target className="size-5" />} title="Recommendation pending" />
      </Card>
    );
  }

  const r = recommendation;

  return (
    <Card>
      <CardHeader title="Recommendation" action={<SignalBadge signal={r.signal} />} />
      <div className="flex items-center gap-4">
        <SignalGauge signal={r.signal} confidence={r.confidence} size={88} strokeWidth={7} label="conf" />
        <div className="min-w-0 flex-1">
          <p className="text-sm leading-relaxed text-text">{r.summary || r.reasoning || "No summary provided."}</p>
          {r.time_horizon ? (
            <p className="mt-1.5 text-xs text-text-faint">Time horizon: {r.time_horizon}</p>
          ) : null}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3 border-t border-border-soft pt-4">
        <div>
          <p className="text-[10px] uppercase tracking-wide text-text-faint">Entry</p>
          <p className="font-mono text-sm font-medium text-text">{formatCurrency(r.entry_price)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-text-faint">Stop loss</p>
          <p className="font-mono text-sm font-medium text-sell">{formatCurrency(r.stop_loss)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-text-faint">Take profit</p>
          <p className="font-mono text-sm font-medium text-buy">{formatCurrency(r.take_profit)}</p>
        </div>
      </div>

      {(r.bull_case || r.bear_case) && (
        <div className="mt-4 grid gap-3 border-t border-border-soft pt-4 sm:grid-cols-2">
          {r.bull_case ? (
            <div className="rounded-lg border border-buy/25 bg-buy-soft p-3">
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-buy">Bull case</p>
              <p className="text-xs leading-relaxed text-text-muted">{r.bull_case}</p>
            </div>
          ) : null}
          {r.bear_case ? (
            <div className="rounded-lg border border-sell/25 bg-sell-soft p-3">
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-sell">Bear case</p>
              <p className="text-xs leading-relaxed text-text-muted">{r.bear_case}</p>
            </div>
          ) : null}
        </div>
      )}
    </Card>
  );
}
