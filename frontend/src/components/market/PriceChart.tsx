"use client";

import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { OhlcvRow } from "@/lib/types";
import { formatCurrency, formatDate } from "@/lib/utils";

export function PriceChart({ rows, tone = "accent" }: { rows: OhlcvRow[]; tone?: "accent" | "buy" | "sell" }) {
  const color =
    tone === "buy" ? "var(--color-buy)" : tone === "sell" ? "var(--color-sell)" : "var(--color-accent)";

  const data = rows
    .filter((r) => r.close !== null)
    .map((r) => ({ date: r.date, close: r.close as number }));

  if (data.length === 0) {
    return (
      <div className="flex h-56 items-center justify-center text-sm text-text-faint">
        No price history available
      </div>
    );
  }

  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <defs>
            <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
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
            tickFormatter={(v: number) => formatCurrency(v, { compact: true })}
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
            formatter={(value) => [formatCurrency(typeof value === "number" ? value : null), "Close"]}
          />
          <Area type="monotone" dataKey="close" stroke={color} strokeWidth={2} fill="url(#priceFill)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
