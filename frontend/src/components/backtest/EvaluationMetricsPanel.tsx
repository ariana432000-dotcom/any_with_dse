import type { EvaluationMetrics } from "@/lib/types";
import { StatCard } from "@/components/ui/StatCard";
import { formatNumber, formatPercent } from "@/lib/utils";

/** Renders the six-metric evaluation methodology (Cumulative/Final Return,
 * Sharpe, Sortino, Max Drawdown, Win Rate, Calmar) as a stat-card grid.
 * Sharpe/Sortino/Calmar come back `null` from the backend when there isn't
 * enough resolved history to compute them meaningfully (see
 * app/services/eval_metrics.py) -- formatNumber/formatPercent already
 * render that as "—" rather than a fabricated 0. */
export function EvaluationMetricsPanel({ metrics }: { metrics: EvaluationMetrics }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <StatCard
        label="Cumulative Return"
        value={formatPercent(metrics.cumulative_return_pct)}
        tone={metrics.cumulative_return_pct >= 0 ? "buy" : "sell"}
        hint={`${metrics.n_trades} trade(s)`}
      />
      <StatCard label="Sharpe Ratio" value={formatNumber(metrics.sharpe_ratio, 2)} />
      <StatCard label="Sortino Ratio" value={formatNumber(metrics.sortino_ratio, 2)} />
      <StatCard
        label="Max Drawdown"
        value={formatPercent(metrics.max_drawdown_pct)}
        tone={metrics.max_drawdown_pct < 0 ? "sell" : "neutral"}
      />
      <StatCard label="Win Rate" value={formatPercent(metrics.win_rate_pct, 0)} />
      <StatCard label="Calmar Ratio" value={formatNumber(metrics.calmar_ratio, 2)} />
    </div>
  );
}
