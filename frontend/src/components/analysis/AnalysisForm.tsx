"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Play } from "lucide-react";
import { analysisApi, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";

export function AnalysisForm({ defaultTicker = "" }: { defaultTicker?: string }) {
  const router = useRouter();
  const [ticker, setTicker] = useState(defaultTicker);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    setSubmitting(true);
    setError(null);
    try {
      const { analysis_id } = await analysisApi.runBackground({ ticker: t });
      router.push(`/analysis/${analysis_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to start analysis");
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title="Run a new analysis"
        subtitle="Dispatches the full TradingAgents / RAEM pipeline for a ticker and streams live progress."
      />
      <form onSubmit={handleSubmit} className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1">
          <label htmlFor="ticker" className="mb-1.5 block text-xs font-medium text-text-muted">
            Ticker
          </label>
          <input
            id="ticker"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            placeholder="AAPL"
            autoComplete="off"
            className="h-10 w-full rounded-lg border border-border bg-bg-raised px-3 font-mono text-sm uppercase tracking-wide text-text placeholder:text-text-faint placeholder:normal-case focus:border-accent"
            maxLength={10}
          />
        </div>
        <Button type="submit" loading={submitting} disabled={!ticker.trim()}>
          {!submitting && <Play className="size-3.5" />}
          Run analysis
        </Button>
      </form>
      {error ? <p className="mt-3 text-xs text-sell">{error}</p> : null}
    </Card>
  );
}
