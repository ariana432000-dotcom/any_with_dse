"use client";

import { useEffect, useState } from "react";
import { useWatchlist } from "@/hooks/useWatchlist";
import { stocksApi, ApiError } from "@/lib/api";
import type { HistoryResponse } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { WatchlistTable } from "@/components/market/WatchlistTable";
import { AddTickerForm } from "@/components/market/AddTickerForm";
import { PriceChart } from "@/components/market/PriceChart";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { formatCurrency, formatNumber } from "@/lib/utils";

export default function WatchlistPage() {
  const { tickers, add, remove, hydrated } = useWatchlist();
  const [selected, setSelected] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (hydrated && !selected && tickers.length > 0) setSelected(tickers[0]);
  }, [hydrated, tickers, selected]);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    stocksApi
      .history(selected, 180)
      .then((res) => {
        if (!cancelled) setHistory(res);
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
  }, [selected]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-xl font-semibold text-text">Watchlist</h1>
          <p className="mt-1 text-sm text-text-muted">
            Keyless live quotes via Yahoo/Stooq. Synced to the backend — this is the ticker
            list the scheduled dataset job tracks too.
          </p>
        </div>
        <AddTickerForm onAdd={add} />
      </div>

      <Card>
        <CardHeader title="Tickers" />
        {tickers.length === 0 ? (
          <p className="py-6 text-center text-sm text-text-faint">Your watchlist is empty — add a ticker above.</p>
        ) : (
          <WatchlistTable tickers={tickers} onRemove={remove} />
        )}
      </Card>

      {selected ? (
        <Card>
          <CardHeader
            title={`${selected} · price history`}
            subtitle="180-day close price, keyless market data."
            action={
              <select
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
                className="rounded-md border border-border bg-bg-raised px-2 py-1 font-mono text-xs uppercase text-text focus:border-accent"
              >
                {tickers.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            }
          />
          {loading ? (
            <LoadingState label={`Loading ${selected}…`} />
          ) : error ? (
            <ErrorState description={error} onRetry={() => setSelected((s) => s)} />
          ) : history ? (
            <>
              <PriceChart rows={history.rows} />
              <div className="mt-4 grid grid-cols-2 gap-3 border-t border-border-soft pt-4 text-xs sm:grid-cols-5">
                <Field label="Last close" value={formatCurrency(history.latest_close)} />
                <Field label="RSI" value={formatNumber(history.indicators.rsi as number)} />
                <Field label="MACD" value={formatNumber(history.indicators.macd as number)} />
                <Field label="50-SMA" value={formatCurrency(history.indicators.close_50_sma as number)} />
                <Field label="Bollinger" value={`${formatCurrency(history.indicators.boll_lb as number)} – ${formatCurrency(history.indicators.boll_ub as number)}`} />
              </div>
            </>
          ) : null}
        </Card>
      ) : null}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="mb-1 text-[10px] uppercase tracking-wide text-text-faint">{label}</p>
      <p className="font-mono text-text">{value}</p>
    </div>
  );
}
