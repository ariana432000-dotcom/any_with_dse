import type { RecommendationState } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { SignalBadge } from "@/components/ui/Badge";
import { formatCurrency } from "@/lib/utils";
import { EmptyState } from "@/components/ui/States";
import { Target } from "lucide-react";

function pctChange(from: number, to: number): string {
  const pct = ((to - from) / from) * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

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
  const currency: "USD" | "BDT" = r.currency === "BDT" ? "BDT" : "USD";
  const hasEntry = r.entry_price !== null && r.entry_price !== undefined;
  const takeProfitPct = hasEntry && r.take_profit != null ? pctChange(r.entry_price!, r.take_profit) : null;
  const stopLossPct = hasEntry && r.stop_loss != null ? pctChange(r.entry_price!, r.stop_loss) : null;

  return (
    <Card>
      <CardHeader title="Recommendation" action={<SignalBadge signal={r.signal} />} />
      <div className="flex items-center gap-4">
        <div className="min-w-0 flex-1">
          <p className="mb-1.5 font-mono text-xs text-text-faint">
            confidence {Math.round(Math.min(1, Math.max(0, r.confidence)) * 100)}%
          </p>
          <p className="text-sm leading-relaxed text-text">{r.summary || r.reasoning || "No summary provided."}</p>
          {r.time_horizon ? (
            <p className="mt-1.5 text-xs text-text-faint">Time horizon: {r.time_horizon}</p>
          ) : null}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3 border-t border-border-soft pt-4">
        <div>
          <p className="text-[10px] uppercase tracking-wide text-text-faint">Entry</p>
          <p className="font-mono text-sm font-medium text-text">{formatCurrency(r.entry_price, { currency: currency })}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-text-faint">Stop loss</p>
          <p className="font-mono text-sm font-medium text-sell">{formatCurrency(r.stop_loss, { currency: currency })}</p>
          {stopLossPct ? <p className="font-mono text-[11px] text-sell/80">{stopLossPct} if hit</p> : null}
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-text-faint">Take profit</p>
          <p className="font-mono text-sm font-medium text-buy">{formatCurrency(r.take_profit, { currency: currency })}</p>
          {takeProfitPct ? <p className="font-mono text-[11px] text-buy/80">{takeProfitPct} if hit</p> : null}
        </div>
      </div>
      {(takeProfitPct || stopLossPct) && (
        <p className="mt-2 text-[11px] text-text-faint">
          Planned exit levels from this analysis, not a price forecast — the %/gain-loss shown is only what
          would result <em>if</em> that level is reached, whenever that happens to be.
        </p>
      )}

      {r.reasoning ? (
        <div className="mt-4 border-t border-border-soft pt-4">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-text-faint">
            Why {r.signal.toString().toUpperCase()}
          </p>
          <p className="text-xs leading-relaxed text-text-muted">{r.reasoning}</p>
        </div>
      ) : null}
    </Card>
  );
}
