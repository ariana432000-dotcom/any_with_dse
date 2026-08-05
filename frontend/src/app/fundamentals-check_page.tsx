"use client";

import { useEffect, useState, type FormEvent } from "react";
import { CheckCircle2, XCircle, HelpCircle } from "lucide-react";
import { useWatchlist } from "@/hooks/useWatchlist";
import { ApiError, stocksApi } from "@/lib/api";
import type { FundamentalsCheckResponse } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { Button } from "@/components/ui/Button";

const METRIC_LABELS: Record<keyof FundamentalsCheckResponse["parsed"], string> = {
  pe_ratio: "P/E Ratio",
  eps: "EPS",
  market_cap: "Market Cap",
  dividend_yield: "Dividend Yield",
};

function StatusBadge({ ok }: { ok: boolean | null }) {
  if (ok === true) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-buy/10 px-3 py-1 text-xs font-medium text-buy">
        <CheckCircle2 className="size-3.5" /> OK
      </span>
    );
  }
  if (ok === false) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-sell/10 px-3 py-1 text-xs font-medium text-sell">
        <XCircle className="size-3.5" /> Failed
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-bg-raised px-3 py-1 text-xs font-medium text-text-muted">
      <HelpCircle className="size-3.5" /> N/A
    </span>
  );
}

export default function FundamentalsCheckPage() {
  const { tickers } = useWatchlist();
  const [ticker, setTicker] = useState(tickers[0] ?? "ISLAMIBANK");
  const [input, setInput] = useState(ticker);
  const [result, setResult] = useState<FundamentalsCheckResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    stocksApi
      .fundamentalsCheck(ticker)
      .then((res) => {
        if (!cancelled) setResult(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to run check");
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
        <h1 className="font-display text-xl font-semibold text-text">Fundamentals Check</h1>
        <p className="mt-1 text-sm text-text-muted">
          One fetch, no LLM calls, no other analysts -- verify the fundamentals data source is
          working for a ticker in seconds, without running a full AI Analysis pass.
        </p>
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
            Check
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
        <CardHeader
          title={`Status · ${ticker}`}
          action={result ? <StatusBadge ok={result.ok} /> : null}
        />
        {loading ? (
          <LoadingState label={`Checking fundamentals for ${ticker}…`} />
        ) : error ? (
          <ErrorState description={error} onRetry={() => setTicker((t) => t)} />
        ) : result ? (
          <div className="space-y-4">
            <p className="text-sm text-text-muted">{result.status}</p>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {(Object.keys(METRIC_LABELS) as Array<keyof typeof METRIC_LABELS>).map((key) => (
                <div key={key} className="rounded-lg border border-border-soft bg-bg-raised p-3">
                  <p className="text-[11px] uppercase tracking-wide text-text-faint">
                    {METRIC_LABELS[key]}
                  </p>
                  <p className="mt-1 font-mono text-sm text-text">
                    {result.parsed[key] ?? "N/A"}
                  </p>
                </div>
              ))}
            </div>

            {result.raw_response ? (
              <div>
                <p className="mb-1.5 text-[11px] uppercase tracking-wide text-text-faint">
                  Raw response (first 500 chars)
                </p>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg border border-border-soft bg-bg-raised p-3 font-mono text-xs text-text-muted">
                  {result.raw_response}
                </pre>
              </div>
            ) : null}
          </div>
        ) : null}
      </Card>
    </div>
  );
}
