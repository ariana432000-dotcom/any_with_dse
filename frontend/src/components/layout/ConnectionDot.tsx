"use client";

import { useHealth } from "@/hooks/useHealth";
import { cn } from "@/lib/utils";

export function ConnectionDot() {
  const { health, loading, error } = useHealth(15_000);
  const ok = !loading && !error && health?.status === "ok";
  const degraded = !loading && !error && health?.status === "degraded";

  return (
    <span
      className={cn(
        "size-2 shrink-0 rounded-full",
        ok && "bg-buy",
        degraded && "bg-hold animate-pulse-dot",
        (error || (!loading && !health)) && "bg-sell",
        loading && "bg-text-faint animate-pulse-dot",
      )}
      title={error ? "Backend unreachable" : health?.status ?? "connecting"}
    />
  );
}
