import type { PortfolioState, RiskState } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { SignalBadge } from "@/components/ui/Badge";
import { formatCurrency, formatPercent } from "@/lib/utils";

export function RiskPortfolioPanel({
  risk,
  portfolio,
}: {
  risk: RiskState | null;
  portfolio: PortfolioState | null;
}) {
  if (!risk && !portfolio) return null;

  return (
    <Card>
      <CardHeader title="Risk & Portfolio Manager" />
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-text-faint">
            Risk assessment
          </p>
          {risk ? (
            <div className="space-y-2">
              <span
                className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                  risk.rating === "HIGH"
                    ? "border-sell/30 bg-sell-soft text-sell"
                    : risk.rating === "LOW"
                      ? "border-buy/30 bg-buy-soft text-buy"
                      : "border-hold/30 bg-hold-soft text-hold"
                }`}
              >
                {risk.rating || "N/A"} risk
              </span>
              {risk.position_sizing ? (
                <p className="text-xs text-text-muted">Position sizing: {risk.position_sizing}</p>
              ) : null}
              {risk.summary ? (
                <p className="text-xs leading-relaxed text-text-muted">{risk.summary}</p>
              ) : null}
              <div className="flex gap-4 pt-1 font-mono text-xs">
                <span className="text-text-faint">
                  SL <span className="text-sell">{formatCurrency(risk.stop_loss)}</span>
                </span>
                <span className="text-text-faint">
                  TP <span className="text-buy">{formatCurrency(risk.take_profit)}</span>
                </span>
              </div>
            </div>
          ) : (
            <p className="text-xs text-text-faint">Not assessed.</p>
          )}
        </div>

        <div>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-text-faint">
            Portfolio decision
          </p>
          {portfolio ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <SignalBadge signal={portfolio.signal} />
                {portfolio.allocation_pct !== null ? (
                  <span className="font-mono text-xs text-text-muted">
                    {formatPercent(portfolio.allocation_pct)} allocation
                  </span>
                ) : null}
              </div>
              {portfolio.rationale ? (
                <p className="text-xs leading-relaxed text-text-muted">{portfolio.rationale}</p>
              ) : null}
            </div>
          ) : (
            <p className="text-xs text-text-faint">Not decided.</p>
          )}
        </div>
      </div>
    </Card>
  );
}
