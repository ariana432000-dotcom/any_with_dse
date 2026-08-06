"use client";

import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { BacktestCurvePoint } from "@/lib/types";
import { formatDate, formatPercent } from "@/lib/utils";

export function EquityCurveChart({ curve }: { curve: BacktestCurvePoint[] }) {
  if (curve.length === 0) {
    return (
      <div className="flex h-56 items-center justify-center text-sm text-text-faint">
        No resolved episodes yet — the curve fills in as episodes resolve.
      </div>
    );
  }

  const final = curve[curve.length - 1].cumulative_pnl_pct;
  const color = final >= 0 ? "var(--color-buy)" : "var(--color-sell)";
  const data = curve.map((c) => ({
    date: c.trade_date,
    cumulative: c.cumulative_pnl_pct,
    pnl: c.pnl_pct,
    signal: c.signal,
    outcome: c.outcome_label,
  }));

  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <defs>
            <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
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
            formatter={(value) => [formatPercent(typeof value === "number" ? value : null), "Cumulative P&L"]}
          />
          <Area type="monotone" dataKey="cumulative" stroke={color} strokeWidth={2} fill="url(#equityFill)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
