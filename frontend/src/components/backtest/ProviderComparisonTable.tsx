import type { EvaluationMetrics } from "@/lib/types";
import { formatNumber, formatPercent } from "@/lib/utils";

const ROWS: { key: keyof EvaluationMetrics; label: string; kind: "pct" | "num" | "count" }[] = [
  { key: "n_trades", label: "Trades", kind: "count" },
  { key: "cumulative_return_pct", label: "Cumulative Return", kind: "pct" },
  { key: "sharpe_ratio", label: "Sharpe Ratio", kind: "num" },
  { key: "sortino_ratio", label: "Sortino Ratio", kind: "num" },
  { key: "max_drawdown_pct", label: "Max Drawdown", kind: "pct" },
  { key: "win_rate_pct", label: "Win Rate", kind: "pct" },
  { key: "calmar_ratio", label: "Calmar Ratio", kind: "num" },
];

/** Side-by-side comparison of the six evaluation metrics across LLM
 * providers (e.g. "anthropic:claude-sonnet-5" vs "kimi:kimi-k3") -- one
 * column per provider tag found in episode metadata (see
 * app/pipeline/llm.py::provider_label and by_llm_provider in
 * app/services/backtest.py). Providers with too few resolved trades to
 * compute Sharpe/Sortino/Calmar show "—" for those cells rather than a
 * fabricated number -- see eval_metrics.py's n<2 guards. */
export function ProviderComparisonTable({
  byProvider,
}: {
  byProvider: Record<string, EvaluationMetrics>;
}) {
  const providers = Object.entries(byProvider).filter(([key]) => key !== "N/A");

  if (providers.length === 0) {
    return (
      <p className="text-xs text-text-faint">
        No provider-tagged episodes yet — this fills in once analyses run with a specific model
        selected (see the &quot;Model&quot; field on Run analysis).
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border-soft text-left text-text-faint">
            <th className="py-1.5 pr-4 font-medium">Metric</th>
            {providers.map(([provider]) => (
              <th key={provider} className="py-1.5 pr-4 font-mono font-medium text-text">
                {provider}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row) => (
            <tr key={row.key} className="border-b border-border-soft/60 last:border-0">
              <td className="py-1.5 pr-4 text-text-muted">{row.label}</td>
              {providers.map(([provider, m]) => {
                const raw = m[row.key];
                const value =
                  row.kind === "pct"
                    ? formatPercent(raw as number, row.key === "win_rate_pct" ? 0 : 2)
                    : row.kind === "count"
                      ? formatNumber(raw as number, 0)
                      : formatNumber(raw as number, 2);
                const tone =
                  row.kind === "pct" && typeof raw === "number"
                    ? raw >= 0
                      ? "text-buy"
                      : "text-sell"
                    : "text-text";
                return (
                  <td key={provider} className={`py-1.5 pr-4 font-mono ${tone}`}>
                    {value}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
