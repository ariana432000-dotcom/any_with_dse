"use client";

import { useEffect, useState } from "react";
import { ApiError, healthApi } from "@/lib/api";
import type { Health } from "@/lib/types";

interface UseHealthResult {
  health: Health | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useHealth(pollMs = 20_000): UseHealthResult {
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [gen, setGen] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await healthApi.get();
        if (!cancelled) {
          setHealth(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to reach backend");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    const interval = pollMs > 0 ? setInterval(load, pollMs) : undefined;
    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
  }, [pollMs, gen]);

  return {
    health,
    loading,
    error,
    refresh: () => {
      setLoading(true);
      setGen((g) => g + 1);
    },
  };
}
