import type { RecommendationState } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { SignalBadge } from "@/components/ui/Badge";
import { formatCurrency } from "@/lib/utils";
import { EmptyState } from "@/components/ui/States";
import { Target } from "lucide-react";

function pctChange(from: number, to: number, isSell: boolean): string {

  const raw = ((to - from) / from) * 100;
  const pct = isSell ? -raw : raw;
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
  const isSell = r.signal?.toString().toUpperCase() === "SELL";
  const hasEntry = r.entry_price !== null && r.entry_price !== undefined;

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

      <div className="mt-4 border-t border-border-soft pt-4">
        <p className="text-[10px] uppercase tracking-wide text-text-faint">Entry</p>
        <p className="font-mono text-sm font-medium text-text">{formatCurrency(r.entry_price, { currency: currency })}</p>
      </div>

      {r.outlook_3d && r.outlook_3d.low !== null && r.outlook_3d.high !== null ? (
        <div className="mt-4 border-t border-border-soft pt-4">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-text-faint">
            {r.outlook_3d.days}-day range (est.)
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-[10px] uppercase tracking-wide text-text-faint">If it drops</p>
              <p className="font-mono text-sm font-medium text-sell">
                {formatCurrency(r.outlook_3d.low, { currency })}
              </p>
              {hasEntry ? (
                <p className="font-mono text-[11px] text-sell/80">
                  {pctChange(r.entry_price!, r.outlook_3d.low, isSell)} if sold here
                </p>
              ) : null}
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wide text-text-faint">If it rises</p>
              <p className="font-mono text-sm font-medium text-buy">
                {formatCurrency(r.outlook_3d.high, { currency })}
              </p>
              {hasEntry ? (
                <p className="font-mono text-[11px] text-buy/80">
                  {pctChange(r.entry_price!, r.outlook_3d.high, isSell)} if sold here
                </p>
              ) : null}
            </div>
          </div>
          <p className="mt-2 text-[11px] text-text-faint">
            A plausible range from this stock&apos;s own recent day-to-day volatility — not a prediction of where
            the price will actually go in {r.outlook_3d.days} days.
          </p>
        </div>
      ) : null}

      {r.reasoning ? (
        <div className="mt-4 border-t border-border-soft pt-4">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-text-faint">
            Why {r.signal.toString().toUpperCase()}
          </p>
          <p className="text-sm leading-relaxed text-text-muted">{r.reasoning}</p>
        </div>
      ) : null}
    </Card>
  );
}
