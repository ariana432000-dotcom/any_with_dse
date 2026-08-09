"use client";

import { Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ProviderCurvePoint } from "@/lib/types";
import { formatDate, formatPercent } from "@/lib/utils";

// Small fixed palette so each provider gets a distinct, stable color
// regardless of name/order. Extend if more than 4 providers ever get
// tagged (openai/groq/ollama joining anthropic/kimi).
const COLORS = ["var(--color-buy)", "var(--color-accent-strong)", "var(--color-sell)", "var(--color-hold)"];

/** Renders one independent cumulative-P&L line per LLM provider on a
 * single chart -- e.g. Kimi vs. Claude Sonnet 5 -- so the two are directly,
 * visually comparable rather than mixed into one shared line. Backed by
 * app/services/backtest.py::_provider_curves(), which computes each
 * provider's cumulative sum from ONLY that provider's own resolved
 * episodes (not one running total split by color). */
export function ProviderEquityCurveChart({
  curveByProvider,
}: {
  curveByProvider: Record<string, ProviderCurvePoint[]>;
}) {
  const providers = Object.keys(curveByProvider).filter((p) => curveByProvider[p]?.length > 0);

  if (providers.length === 0) {
    return (
      <div className="flex h-56 items-center justify-center text-center text-sm text-text-faint">
        No provider-tagged resolved episodes yet — this fills in once a model-tagged analysis
        resolves (see the &quot;Model&quot; field on Run analysis).
      </div>
    );
  }

  // Merge every provider's independent series into one array keyed by
  // trade_date, e.g. { date, "kimi:kimi-k3": -1.9, "anthropic:claude-sonnet-5": 3.2 }.
  // A provider's value is only set on dates it actually has an episode;
  // connectNulls (below) draws a continuous line across the gaps instead
  // of dropping to zero between that provider's own points.
  const dateSet = new Set<string>();
  providers.forEach((p) => curveByProvider[p].forEach((pt) => dateSet.add(pt.trade_date)));
  const dates = Array.from(dateSet).sort();

  const merged = dates.map((date) => {
    const row: Record<string, string | number | null> = { date };
    providers.forEach((p) => {
      const pt = curveByProvider[p].find((x) => x.trade_date === date);
      row[p] = pt ? pt.cumulative_pnl_pct : null;
    });
    return row;
  });

  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={merged} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <XAxis
            dataKey="date"
            tickFormatter={(v: string) => formatDate(v)}
            tick={{ fill: "var(--color-text-faint)", fontSize: 10 }}
            axisLine={{ stroke: "var(--color-border)" }}
            tickLine={false}
            minTickGap={40}
          />
          <YAxis
            domain={["auto", "auto"]}
            tick={{ fill: "var(--color-text-faint)", fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            width={56}
            tickFormatter={(v: number) => formatPercent(v, 0)}
          />
          <Tooltip
            contentStyle={{
              background: "var(--color-panel)",
              border: "1px solid var(--color-border)",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "var(--color-text-muted)" }}
            labelFormatter={(v) => formatDate(typeof v === "string" ? v : undefined)}
            formatter={(value, name) => [formatPercent(typeof value === "number" ? value : null), name]}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {providers.map((p, i) => (
            <Line
              key={p}
              type="monotone"
              dataKey={p}
              name={p}
              stroke={COLORS[i % COLORS.length]}
              strokeWidth={2}
              dot={{ r: 3 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
