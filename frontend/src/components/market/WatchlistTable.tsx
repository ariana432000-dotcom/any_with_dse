"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { stocksApi } from "@/lib/api";
import type { QuoteResponse } from "@/lib/types";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/States";

interface Row {
  ticker: string;
  quote: QuoteResponse | null;
  error: boolean;
}

export function WatchlistTable({
  tickers,
  onRemove,
}: {
  tickers: string[];
  onRemove?: (ticker: string) => void;
}) {
  const [rows, setRows] = useState<Record<string, Row>>({});

  useEffect(() => {
    let cancelled = false;
    tickers.forEach(async (ticker) => {
      setRows((prev) => ({ ...prev, [ticker]: prev[ticker] ?? { ticker, quote: null, error: false } }));
      try {
        const quote = await stocksApi.quote(ticker);
        if (!cancelled) setRows((prev) => ({ ...prev, [ticker]: { ticker, quote, error: false } }));
      } catch {
        if (!cancelled) setRows((prev) => ({ ...prev, [ticker]: { ticker, quote: null, error: true } }));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [tickers]);

  if (tickers.length === 0) return null;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border-soft text-left text-xs uppercase tracking-wider text-text-faint">
            <th className="py-2 pr-4 font-medium">Ticker</th>
            <th className="py-2 pr-4 font-medium">Price</th>
            <th className="py-2 pr-4 font-medium">Change</th>
            <th className="py-2 pr-4 font-medium hidden sm:table-cell">Volume</th>
            <th className="py-2 pr-4 font-medium hidden md:table-cell">Range</th>
            <th className="py-2 pr-0 font-medium" />
          </tr>
        </thead>
        <tbody>
          {tickers.map((ticker) => {
            const row = rows[ticker];
            const q = row?.quote;
            const up = (q?.change_pct ?? 0) >= 0;
            return (
              <tr key={ticker} className="border-b border-border-soft/60 last:border-0">
                <td className="py-3 pr-4">
                  <Link
                    href={`/analysis?ticker=${ticker}`}
                    className="font-mono text-sm font-semibold text-text hover:text-accent"
                  >
                    {ticker}
                  </Link>
                </td>
                <td className="py-3 pr-4 font-mono tabular-nums text-text">
                  {row?.error ? (
                    <span className="text-text-faint">n/a</span>
                  ) : q ? (
                    formatCurrency(q.price)
                  ) : (
                    <Skeleton className="h-4 w-16" />
                  )}
                </td>
                <td className="py-3 pr-4">
                  {row?.error ? (
                    <span className="text-text-faint">—</span>
                  ) : q ? (
                    <span
                      className={cn(
                        "font-mono text-xs font-medium tabular-nums",
                        up ? "text-buy" : "text-sell",
                      )}
                    >
                      {formatPercent(q.change_pct)}
                    </span>
                  ) : (
                    <Skeleton className="h-4 w-12" />
                  )}
                </td>
                <td className="hidden py-3 pr-4 font-mono text-xs tabular-nums text-text-muted sm:table-cell">
                  {q?.volume ? q.volume.toLocaleString() : "—"}
                </td>
                <td className="hidden py-3 pr-4 font-mono text-xs tabular-nums text-text-muted md:table-cell">
                  {q?.low && q?.high ? `${formatCurrency(q.low)} – ${formatCurrency(q.high)}` : "—"}
                </td>
                <td className="py-3 pr-0 text-right">
                  {onRemove ? (
                    <button
                      onClick={() => onRemove(ticker)}
                      className="text-text-faint hover:text-sell"
                      aria-label={`Remove ${ticker} from watchlist`}
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
