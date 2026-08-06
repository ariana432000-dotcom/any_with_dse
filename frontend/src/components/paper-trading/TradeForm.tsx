"use client";

import { type FormEvent, useState } from "react";
import { paperTradingApi, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";

export function TradeForm({ tickers, onTraded }: { tickers: string[]; onTraded: () => void }) {
  const [ticker, setTicker] = useState(tickers[0] ?? "");
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [shares, setShares] = useState("10");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const n = parseFloat(shares);
    if (!ticker.trim() || !n || n <= 0) {
      setError("Enter a ticker and a positive share count.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await paperTradingApi.trade(ticker.trim().toUpperCase(), side, n);
      onTraded();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Trade failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
      <div>
        <label className="mb-1 block text-[10px] uppercase tracking-wide text-text-faint">Ticker</label>
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          list="paper-trading-tickers"
          placeholder="AAPL"
          className="w-28 rounded-md border border-border bg-bg-raised px-2 py-1.5 font-mono text-xs uppercase text-text focus:border-accent"
        />
        <datalist id="paper-trading-tickers">
          {tickers.map((t) => (
            <option key={t} value={t} />
          ))}
        </datalist>
      </div>
      <div>
        <label className="mb-1 block text-[10px] uppercase tracking-wide text-text-faint">Side</label>
        <select
          value={side}
          onChange={(e) => setSide(e.target.value as "BUY" | "SELL")}
          className="h-[34px] rounded-md border border-border bg-bg-raised px-2 font-mono text-xs uppercase text-text focus:border-accent"
        >
          <option value="BUY">BUY</option>
          <option value="SELL">SELL</option>
        </select>
      </div>
      <div>
        <label className="mb-1 block text-[10px] uppercase tracking-wide text-text-faint">Shares</label>
        <input
          type="number"
          min="0"
          step="any"
          value={shares}
          onChange={(e) => setShares(e.target.value)}
          className="w-24 rounded-md border border-border bg-bg-raised px-2 py-1.5 font-mono text-xs text-text focus:border-accent"
        />
      </div>
      <Button type="submit" loading={submitting} size="sm">
        Simulate {side}
      </Button>
      {error ? <p className="basis-full text-xs text-sell">{error}</p> : null}
    </form>
  );
}
