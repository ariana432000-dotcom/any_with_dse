"use client";

import { useEffect, useState } from "react";
import { datasetApi, ApiError } from "@/lib/api";
import type { DatasetRow, DatasetSummary } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge, SignalBadge } from "@/components/ui/Badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { cn } from "@/lib/utils";
import { Database, Download } from "lucide-react";

export default function DatasetPage() {
  const [datasets, setDatasets] = useState<DatasetSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [rows, setRows] = useState<DatasetRow[] | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingRows, setLoadingRows] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    datasetApi
      .list()
      .then((res) => {
        if (cancelled) return;
        setDatasets(res.datasets);
        if (res.datasets.length > 0) setSelected(res.datasets[0].ticker);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load datasets");
      })
      .finally(() => {
        if (!cancelled) setLoadingList(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setLoadingRows(true);
    datasetApi
      .rows(selected, 500)
      .then((res) => {
        if (!cancelled) setRows(res.rows);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load rows");
      })
      .finally(() => {
        if (!cancelled) setLoadingRows(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-xl font-semibold text-text">Dataset Explorer</h1>
        <p className="mt-1 text-sm text-text-muted">
          The scheduled job appends one row per completed analysis to a CSV per ticker, building a
          historical dataset of fetched data + agent decisions over time.
        </p>
      </div>

      {loadingList ? (
        <LoadingState label="Loading datasets…" />
      ) : error && !datasets ? (
        <ErrorState description={error} />
      ) : !datasets || datasets.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Database className="size-5" />}
            title="No dataset files yet"
            description="Once the scheduled dataset job runs (or you run a manual analysis), a CSV will appear here per ticker."
          />
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader title="Tracked datasets" subtitle={`${datasets.length} ticker(s)`} />
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              {datasets.map((d) => (
                <button
                  key={d.ticker}
                  onClick={() => setSelected(d.ticker)}
                  className={cn(
                    "rounded-lg border px-3 py-2.5 text-left transition-colors",
                    selected === d.ticker
                      ? "border-accent/40 bg-accent-soft"
                      : "border-border-soft bg-bg-raised hover:bg-panel-hover",
                  )}
                >
                  <p className="font-mono text-sm font-semibold text-text">{d.ticker}</p>
                  <p className="text-[11px] text-text-faint">
                    {d.rows} row{d.rows === 1 ? "" : "s"}
                  </p>
                </button>
              ))}
            </div>
          </Card>

          {selected ? (
            <Card>
              <CardHeader
                title={`${selected} dataset`}
                subtitle={rows ? `${rows.length} row(s), newest first` : undefined}
                action={
                  <a
                    href={datasetApi.downloadUrl(selected)}
                    className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-xs font-medium text-text-muted hover:border-accent hover:text-accent"
                  >
                    <Download className="size-3.5" />
                    Download CSV
                  </a>
                }
              />
              {loadingRows ? (
                <LoadingState label={`Loading ${selected} rows…`} />
              ) : !rows || rows.length === 0 ? (
                <EmptyState icon={<Database className="size-5" />} title="No rows yet for this ticker" />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-border-soft text-left uppercase tracking-wider text-text-faint">
                        <th className="py-2 pr-3 font-medium">Date</th>
                        <th className="py-2 pr-3 font-medium">Signal</th>
                        <th className="py-2 pr-3 font-medium">Effective</th>
                        <th className="py-2 pr-3 font-medium">Confidence</th>
                        <th className="py-2 pr-3 font-medium">Regime</th>
                        <th className="py-2 pr-3 font-medium">Macro</th>
                        <th className="py-2 pr-3 font-medium">Verifier</th>
                        <th className="py-2 pr-3 font-medium">RSI</th>
                        <th className="py-2 pr-3 font-medium">MACD</th>
                        <th className="py-2 pr-0 font-medium">News</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r, i) => (
                        <tr key={`${r.analysis_id}-${i}`} className="border-b border-border-soft/60 last:border-0">
                          <td className="py-2 pr-3 font-mono text-text-muted">{r.date}</td>
                          <td className="py-2 pr-3">
                            <SignalBadge signal={r.signal} />
                          </td>
                          <td className="py-2 pr-3">
                            {r.auto_overridden === "True" ? (
                              <SignalBadge signal={r.effective_signal} />
                            ) : (
                              <span className="text-text-faint">—</span>
                            )}
                          </td>
                          <td className="py-2 pr-3 font-mono tabular-nums text-text-muted">
                            {r.confidence ? `${Math.round(parseFloat(r.confidence) * 100)}%` : "—"}
                          </td>
                          <td className="py-2 pr-3 text-text-muted">{r.regime || "—"}</td>
                          <td className="py-2 pr-3 text-text-muted">{r.macro_regime || "—"}</td>
                          <td className="py-2 pr-3">
                            {r.verifier_status ? (
                              <Badge tone={r.verifier_status === "FLAGGED" ? "sell" : "buy"}>
                                {r.verifier_status}
                              </Badge>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="py-2 pr-3 font-mono text-text-muted">{r.rsi || "—"}</td>
                          <td className="py-2 pr-3 font-mono text-text-muted">{r.macd || "—"}</td>
                          <td className="py-2 pr-0 text-text-muted">{r.news_sentiment || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          ) : null}
        </>
      )}
    </div>
  );
}
