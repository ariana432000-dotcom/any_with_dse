"use client";

import { useCallback, useEffect, useState } from "react";
import { paperTradingApi, ApiError } from "@/lib/api";
import type { PaperPortfolio, PaperTrade } from "@/lib/types";
import { useWatchlist } from "@/hooks/useWatchlist";
import { Card, CardHeader } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TradeForm } from "@/components/paper-trading/TradeForm";
import { formatCurrency, formatDateTime, formatPercent } from "@/lib/utils";
import { Wallet } from "lucide-react";

export default function PaperTradingPage() {
  const { tickers } = useWatchlist();
  const [portfolio, setPortfolio] = useState<PaperPortfolio | null>(null);
  const [trades, setTrades] = useState<PaperTrade[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);

  const refresh = useCallback(() => {
    setLoading(true);
    Promise.all([paperTradingApi.portfolio(), paperTradingApi.trades(50)])
      .then(([p, t]) => {
        setPortfolio(p);
        setTrades(t.trades);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Failed to load paper trading portfolio");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleReset() {
    if (!window.confirm("Reset the paper trading portfolio? This clears all positions and trade history.")) {
      return;
    }
    setResetting(true);
    try {
      await paperTradingApi.reset();
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Reset failed");
    } finally {
      setResetting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-xl font-semibold text-text">Paper Trading</h1>
          <p className="mt-1 text-sm text-text-muted">
            A simulated portfolio — no real money. Fills use live keyless quotes, so P&amp;L tracks
            real prices.
          </p>
        </div>
        <Button variant="danger" size="sm" onClick={handleReset} loading={resetting}>
          Reset portfolio
        </Button>
      </div>

      {loading && !portfolio ? (
        <LoadingState label="Loading portfolio…" />
      ) : error && !portfolio ? (
        <ErrorState description={error} onRetry={refresh} />
      ) : portfolio ? (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <StatCard label="Equity" value={formatCurrency(portfolio.equity)} />
            <StatCard label="Cash" value={formatCurrency(portfolio.cash)} />
            <StatCard
              label="Total return"
              value={formatPercent(portfolio.total_return_pct)}
              tone={portfolio.total_return_pct >= 0 ? "buy" : "sell"}
            />
            <StatCard
              label="Realized P&L"
              value={formatCurrency(portfolio.realized_pnl)}
              tone={portfolio.realized_pnl >= 0 ? "buy" : "sell"}
            />
            <StatCard
              label="Unrealized P&L"
              value={formatCurrency(portfolio.unrealized_pnl)}
              tone={portfolio.unrealized_pnl >= 0 ? "buy" : "sell"}
            />
          </div>

          <Card>
            <CardHeader title="Simulate a trade" subtitle="Fills at the current keyless quote price." />
            <TradeForm tickers={tickers} onTraded={refresh} />
          </Card>

          <Card>
            <CardHeader title="Open positions" subtitle={`${portfolio.positions.length} position(s)`} />
            {portfolio.positions.length === 0 ? (
              <EmptyState icon={<Wallet className="size-5" />} title="No open positions" description="Simulate a BUY above to open one." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border-soft text-left uppercase tracking-wider text-text-faint">
                      <th className="py-2 pr-3 font-medium">Ticker</th>
                      <th className="py-2 pr-3 font-medium">Shares</th>
                      <th className="py-2 pr-3 font-medium">Avg cost</th>
                      <th className="py-2 pr-3 font-medium">Price</th>
                      <th className="py-2 pr-3 font-medium">Market value</th>
                      <th className="py-2 pr-0 font-medium">Unrealized P&amp;L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio.positions.map((p) => (
                      <tr key={p.ticker} className="border-b border-border-soft/60 last:border-0">
                        <td className="py-2 pr-3 font-mono font-semibold text-text">{p.ticker}</td>
                        <td className="py-2 pr-3 text-text-muted">{p.shares}</td>
                        <td className="py-2 pr-3 font-mono text-text-muted">{formatCurrency(p.avg_cost)}</td>
                        <td className="py-2 pr-3 font-mono text-text-muted">{formatCurrency(p.current_price)}</td>
                        <td className="py-2 pr-3 font-mono text-text-muted">{formatCurrency(p.market_value)}</td>
                        <td className={`py-2 pr-0 font-mono ${p.unrealized_pnl >= 0 ? "text-buy" : "text-sell"}`}>
                          {formatCurrency(p.unrealized_pnl)} ({formatPercent(p.unrealized_pnl_pct)})
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card>
            <CardHeader title="Trade log" subtitle={trades ? `${trades.length} trade(s), newest first` : undefined} />
            {!trades || trades.length === 0 ? (
              <EmptyState icon={<Wallet className="size-5" />} title="No trades yet" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border-soft text-left uppercase tracking-wider text-text-faint">
                      <th className="py-2 pr-3 font-medium">When</th>
                      <th className="py-2 pr-3 font-medium">Ticker</th>
                      <th className="py-2 pr-3 font-medium">Side</th>
                      <th className="py-2 pr-3 font-medium">Shares</th>
                      <th className="py-2 pr-3 font-medium">Price</th>
                      <th className="py-2 pr-3 font-medium">Value</th>
                      <th className="py-2 pr-0 font-medium">Realized P&amp;L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((t, i) => (
                      <tr key={t.id ?? i} className="border-b border-border-soft/60 last:border-0">
                        <td className="py-2 pr-3 text-text-faint">{formatDateTime(t.created_at)}</td>
                        <td className="py-2 pr-3 font-mono font-semibold text-text">{t.ticker}</td>
                        <td className="py-2 pr-3">
                          <Badge tone={t.side === "BUY" ? "buy" : "sell"}>{t.side}</Badge>
                        </td>
                        <td className="py-2 pr-3 text-text-muted">{t.shares}</td>
                        <td className="py-2 pr-3 font-mono text-text-muted">{formatCurrency(t.price)}</td>
                        <td className="py-2 pr-3 font-mono text-text-muted">{formatCurrency(t.value)}</td>
                        <td className={`py-2 pr-0 font-mono ${t.realized_pnl > 0 ? "text-buy" : t.realized_pnl < 0 ? "text-sell" : "text-text-faint"}`}>
                          {t.realized_pnl ? formatCurrency(t.realized_pnl) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      ) : null}
    </div>
  );
}
