"use client";

import { useCallback, useEffect, useState } from "react";
import { DEFAULT_WATCHLIST, WATCHLIST_STORAGE_KEY } from "@/lib/constants";
import { watchlistApi, ApiError } from "@/lib/api";

/**
 * The watchlist is now server-side (backend/app/services/watchlist_store.py)
 * so the scheduled dataset-export job can read it too — it's not just a UI
 * preference anymore. localStorage is kept as an instant-paint cache and an
 * offline fallback if the backend is briefly unreachable; the backend is the
 * source of truth once it responds.
 */
export function useWatchlist() {
  const [tickers, setTickers] = useState<string[]>(DEFAULT_WATCHLIST);
  const [hydrated, setHydrated] = useState(false);

  const cacheLocally = useCallback((next: string[]) => {
    try {
      window.localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(next));
    } catch {
      // ignore quota errors
    }
  }, []);

  // 1) Instant paint from the local cache.
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(WATCHLIST_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as string[];
        if (Array.isArray(parsed) && parsed.length > 0) setTickers(parsed);
      }
    } catch {
      // ignore corrupt storage
    } finally {
      setHydrated(true);
    }
  }, []);

  // 2) Reconcile with the backend (source of truth) once it responds.
  useEffect(() => {
    let cancelled = false;
    watchlistApi
      .list()
      .then((res) => {
        if (cancelled) return;
        if (res.tickers.length > 0) {
          setTickers(res.tickers);
          cacheLocally(res.tickers);
        }
      })
      .catch(() => {
        // backend unreachable — keep using the local cache silently
      });
    return () => {
      cancelled = true;
    };
  }, [cacheLocally]);

  const add = useCallback(
    (ticker: string) => {
      const t = ticker.trim().toUpperCase();
      if (!t || tickers.includes(t)) return;
      const next = [...tickers, t];
      setTickers(next);
      cacheLocally(next);
      watchlistApi.add(t).catch((err) => {
        console.warn("watchlist add failed to sync to backend:", err instanceof ApiError ? err.message : err);
      });
    },
    [tickers, cacheLocally],
  );

  const remove = useCallback(
    (ticker: string) => {
      const next = tickers.filter((t) => t !== ticker);
      setTickers(next);
      cacheLocally(next);
      watchlistApi.remove(ticker).catch((err) => {
        console.warn("watchlist remove failed to sync to backend:", err instanceof ApiError ? err.message : err);
      });
    },
    [tickers, cacheLocally],
  );

  return { tickers, add, remove, hydrated };
}
