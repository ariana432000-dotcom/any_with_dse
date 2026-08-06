"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useWatchlist } from "@/hooks/useWatchlist";
import { ApiError, stocksApi } from "@/lib/api";
import type { NewsItem } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { NewsList } from "@/components/market/NewsList";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { Button } from "@/components/ui/Button";

export default function NewsPage() {
  const { tickers } = useWatchlist();
  const [ticker, setTicker] = useState(tickers[0] ?? "AAPL");
  const [input, setInput] = useState(ticker);
  const [items, setItems] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    stocksApi
      .news(ticker, 12)
      .then((res) => {
        if (!cancelled) setItems(res.items);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load news");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  function submit(e: FormEvent) {
    e.preventDefault();
    const t = input.trim().toUpperCase();
    if (t) setTicker(t);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-xl font-semibold text-text">News</h1>
        <p className="mt-1 text-sm text-text-muted">Keyless headlines via Google News RSS, per ticker.</p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <form onSubmit={submit} className="flex items-center gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ticker"
            className="h-9 w-32 rounded-lg border border-border bg-bg-raised px-3 font-mono text-xs uppercase text-text placeholder:text-text-faint placeholder:normal-case focus:border-accent"
            maxLength={10}
          />
          <Button type="submit" size="sm" variant="secondary">
            Search
          </Button>
        </form>
        {tickers.map((t) => (
          <button
            key={t}
            onClick={() => {
              setTicker(t);
              setInput(t);
            }}
            className={`rounded-full border px-3 py-1 font-mono text-xs ${
              t === ticker
                ? "border-accent bg-accent-soft text-accent-strong"
                : "border-border text-text-muted hover:text-text"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <Card>
        <CardHeader title={`Headlines · ${ticker}`} />
        {loading ? (
          <LoadingState label={`Fetching news for ${ticker}…`} />
        ) : error ? (
          <ErrorState description={error} onRetry={() => setTicker((t) => t)} />
        ) : (
          <NewsList items={items} ticker={ticker} />
        )}
      </Card>
    </div>
  );
}
