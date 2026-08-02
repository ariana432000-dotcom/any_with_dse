"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { analysisApi, ApiError } from "@/lib/api";
import type { AnalysisHistoryItem } from "@/lib/types";
import { AnalysisForm } from "@/components/analysis/AnalysisForm";
import { AnalysisHistoryTable } from "@/components/analysis/AnalysisHistoryTable";
import { Card, CardHeader } from "@/components/ui/Card";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { useWatchlist } from "@/hooks/useWatchlist";

export function AnalysisPageContent() {
  const searchParams = useSearchParams();
  const initialTicker = searchParams.get("ticker") ?? "";
  const { tickers } = useWatchlist();

  const [ticker, setTicker] = useState(initialTicker || tickers[0] || "AAPL");
  const [items, setItems] = useState<AnalysisHistoryItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialTicker) setTicker(initialTicker);
  }, [initialTicker]);

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    setLoading(true);
    analysisApi
      .tickerHistory(ticker, 25)
      .then((res) => {
        if (!cancelled) {
          setItems(res.analyses);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load history");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-xl font-semibold text-text">AI Analysis</h1>
        <p className="mt-1 text-sm text-text-muted">
          Run the full TradingAgents / RAEM pipeline and review past runs per ticker.
        </p>
      </div>

      <AnalysisForm defaultTicker={initialTicker} />

      <Card>
        <CardHeader
          title="History"
          subtitle={
            <span className="flex items-center gap-2">
              for
              <select
                value={ticker}
                onChange={(e) => setTicker(e.target.value)}
                className="rounded-md border border-border bg-bg-raised px-2 py-0.5 font-mono text-xs uppercase text-text focus:border-accent"
              >
                {[...new Set([ticker, ...tickers])].filter(Boolean).map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </span>
          }
        />
        {loading ? (
          <LoadingState label={`Loading history for ${ticker}…`} />
        ) : error ? (
          <ErrorState description={error} onRetry={() => setTicker((t) => t)} />
        ) : (
          <AnalysisHistoryTable items={items ?? []} />
        )}
      </Card>
    </div>
  );
}
