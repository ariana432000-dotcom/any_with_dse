"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { analysisApi, ApiError } from "@/lib/api";
import type { AnalysisResponse } from "@/lib/types";

interface UseAnalysisResult {
  analysis: AnalysisResponse | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

const ACTIVE_STATUSES = new Set(["PENDING", "RUNNING"]);

/** Fetches an analysis by id and polls while it's still in flight. */
export function useAnalysis(analysisId: string, pollMs = 3_000): UseAnalysisResult {
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await analysisApi.get(analysisId);
      setAnalysis(data);
      setError(null);
      if (ACTIVE_STATUSES.has(data.status)) {
        timerRef.current = setTimeout(load, pollMs);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        // Not persisted yet (first tick of a background run) — keep polling briefly.
        timerRef.current = setTimeout(load, pollMs);
        return;
      }
      setError(err instanceof ApiError ? err.message : "Failed to load analysis");
    } finally {
      setLoading(false);
    }
  }, [analysisId, pollMs]);

  useEffect(() => {
    setLoading(true);
    load();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [load]);

  return {
    analysis,
    loading,
    error,
    refresh: () => {
      setLoading(true);
      load();
    },
  };
}
