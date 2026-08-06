"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { CheckCircle2, Clock, FileText, UploadCloud } from "lucide-react";
import { useWatchlist } from "@/hooks/useWatchlist";
import { ApiError, stocksApi } from "@/lib/api";
import type { DseReportsListResponse } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { Button } from "@/components/ui/Button";

export default function ReportsPage() {
  const { tickers } = useWatchlist();
  const [ticker, setTicker] = useState(tickers[0] ?? "SQURPHARMA");
  const [tickerInput, setTickerInput] = useState(ticker);
  const [fiscalYear, setFiscalYear] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [listing, setListing] = useState<DseReportsListResponse | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadedOk, setUploadedOk] = useState<string | null>(null);

  const refreshList = useCallback((t: string) => {
    if (!t) return;
    setLoadingList(true);
    setListError(null);
    stocksApi
      .listReports(t)
      .then(setListing)
      .catch((err) => setListError(err instanceof ApiError ? err.message : "Failed to load reports"))
      .finally(() => setLoadingList(false));
  }, []);

  useEffect(() => {
    refreshList(ticker);
  }, [ticker, refreshList]);

  function submitTicker(e: FormEvent) {
    e.preventDefault();
    const t = tickerInput.trim().toUpperCase();
    if (t) setTicker(t);
  }

  async function submitUpload(e: FormEvent) {
    e.preventDefault();
    setUploadError(null);
    setUploadedOk(null);
    const fy = fiscalYear.trim();
    if (!fy) {
      setUploadError("Enter a fiscal year (e.g. 2025).");
      return;
    }
    if (!file) {
      setUploadError("Choose a PDF file first.");
      return;
    }
    setUploading(true);
    try {
      await stocksApi.uploadReport(ticker, fy, file);
      setUploadedOk(`Uploaded ${ticker} · FY${fy}. It'll be read the next time fundamentals run for this ticker.`);
      setFile(null);
      setFiscalYear("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      refreshList(ticker);
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-xl font-semibold text-text">Annual Reports (PDF)</h1>
        <p className="mt-1 max-w-2xl text-sm text-text-muted">
          dsebd.org doesn&apos;t allow automated download of annual reports, so quarterly/annual
          financial-statement fields (net income, EBITDA, debt, etc.) for DSE tickers only fill in
          once you upload the report PDF yourself here. Download it from dsebd.org or the
          company&apos;s investor-relations page, then upload it below.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <form onSubmit={submitTicker} className="flex items-center gap-2">
          <input
            value={tickerInput}
            onChange={(e) => setTickerInput(e.target.value)}
            placeholder="Ticker"
            className="h-9 w-32 rounded-lg border border-border bg-bg-raised px-3 font-mono text-xs uppercase text-text placeholder:text-text-faint placeholder:normal-case focus:border-accent"
            maxLength={12}
          />
          <Button type="submit" size="sm" variant="secondary">
            Switch
          </Button>
        </form>
        {tickers.map((t) => (
          <button
            key={t}
            onClick={() => {
              setTicker(t);
              setTickerInput(t);
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
        <CardHeader title={`Upload · ${ticker}`} />
        <form onSubmit={submitUpload} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-[160px_1fr]">
            <div>
              <label className="mb-1.5 block text-[11px] uppercase tracking-wide text-text-faint">
                Fiscal Year
              </label>
              <input
                value={fiscalYear}
                onChange={(e) => setFiscalYear(e.target.value)}
                placeholder="2025"
                className="h-10 w-full rounded-lg border border-border bg-bg-raised px-3 font-mono text-sm text-text placeholder:text-text-faint focus:border-accent"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-[11px] uppercase tracking-wide text-text-faint">
                Annual Report PDF
              </label>
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="block w-full text-sm text-text-muted file:mr-3 file:rounded-lg file:border file:border-border file:bg-bg-raised file:px-3 file:py-2 file:text-xs file:font-medium file:text-text hover:file:border-accent"
              />
            </div>
          </div>

          {uploadError && <p className="text-sm text-sell">{uploadError}</p>}
          {uploadedOk && (
            <p className="flex items-center gap-1.5 text-sm text-buy">
              <CheckCircle2 className="size-4" /> {uploadedOk}
            </p>
          )}

          <Button type="submit" disabled={uploading} className="gap-1.5">
            <UploadCloud className="size-4" />
            {uploading ? "Uploading…" : "Upload PDF"}
          </Button>
        </form>
      </Card>

      <Card>
        <CardHeader title={`On file · ${ticker}`} />
        {loadingList ? (
          <LoadingState label={`Checking uploaded reports for ${ticker}…`} />
        ) : listError ? (
          <ErrorState description={listError} onRetry={() => refreshList(ticker)} />
        ) : listing && listing.uploaded_fiscal_years.length > 0 ? (
          <ul className="divide-y divide-border-soft">
            {listing.uploaded_fiscal_years.map((fy) => {
              const extracted = listing.extracted_fiscal_years.includes(fy);
              return (
                <li key={fy} className="flex items-center justify-between py-2.5">
                  <span className="flex items-center gap-2 font-mono text-sm text-text">
                    <FileText className="size-4 text-text-faint" /> FY{fy}
                  </span>
                  {extracted ? (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-buy/10 px-3 py-1 text-xs font-medium text-buy">
                      <CheckCircle2 className="size-3.5" /> Extracted
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-bg-raised px-3 py-1 text-xs font-medium text-text-muted">
                      <Clock className="size-3.5" /> Pending — reads on next Fundamentals Analyst run
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="py-6 text-center text-sm text-text-muted">
            No reports uploaded yet for {ticker}.
          </p>
        )}
      </Card>
    </div>
  );
}
