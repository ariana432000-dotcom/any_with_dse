"use client";

import { useEffect, useState } from "react";
import { backtestApi, ApiError } from "@/lib/api";
import type { BacktestResponse } from "@/lib/types";
import { useWatchlist } from "@/hooks/useWatchlist";
import { Card, CardHeader } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { EquityCurveChart } from "@/components/backtest/EquityCurveChart";
import { BucketTable } from "@/components/backtest/BucketTable";
import { formatPercent } from "@/lib/utils";
import { BarChart3 } from "lucide-react";

const ALL = "__ALL__";

export default function BacktestPage() {
  const { tickers } = useWatchlist();
  const [selected, setSelected] = useState<string>(ALL);
  const [data, setData] = useState<BacktestResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const req = selected === ALL ? backtestApi.all() : backtestApi.forTicker(selected);
    req
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load backtest");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-xl font-semibold text-text">Backtest &amp; Accuracy</h1>
          <p className="mt-1 text-sm text-text-muted">
            Win rate and P&amp;L over every RESOLVED decision — outcomes resolve automatically
            once enough days have passed (see &quot;Outcome Backfill&quot; on each analysis).
          </p>
        </div>
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          className="rounded-md border border-border bg-bg-raised px-2 py-1.5 font-mono text-xs uppercase text-text focus:border-accent"
        >
          <option value={ALL}>All tickers</option>
          {tickers.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      {loading ? (
        <LoadingState label="Loading backtest…" />
      ) : error ? (
        <ErrorState description={error} onRetry={() => setSelected((s) => s)} />
      ) : !data || data.resolved_episodes === 0 ? (
        <Card>
          <EmptyState
            icon={<BarChart3 className="size-5" />}
            title="No resolved episodes yet"
            description="Run a few analyses and give them a day or two — outcomes resolve automatically using the next close price."
          />
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label="Resolved" value={data.resolved_episodes} hint={`${data.pending_episodes} pending`} />
            <StatCard label="Win rate" value={formatPercent(data.win_rate * 100, 0)} />
            <StatCard
              label="Avg P&L"
              value={formatPercent(data.avg_pnl_pct)}
              tone={data.avg_pnl_pct >= 0 ? "buy" : "sell"}
            />
            <StatCard label="Win / Loss / Flat" value={`${data.wins} / ${data.losses} / ${data.flats}`} />
          </div>

          <Card>
            <CardHeader
              title="Cumulative P&L"
              subtitle="Sum of realized P&L across resolved episodes, in trade-date order."
            />
            <EquityCurveChart curve={data.curve} />
          </Card>

          <Card>
            <CardHeader title="Breakdowns" subtitle="Where the system's edge (or lack of it) actually comes from." />
            <div className="grid gap-6 sm:grid-cols-2">
              <BucketTable title="By signal" buckets={data.by_signal} />
              <BucketTable title="By stock regime" buckets={data.by_regime} />
              <BucketTable title="By macro regime" buckets={data.by_macro_regime} />
              <BucketTable title="By verifier status" buckets={data.by_verifier_status} />
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
