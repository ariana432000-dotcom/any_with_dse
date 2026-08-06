"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/ui/States";

export default function AnalysisDetailError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Analysis detail error:", error);
  }, [error]);

  return (
    <ErrorState
      title="Couldn't load this analysis"
      description={error.message || "It may not exist, or the backend is unreachable."}
      onRetry={reset}
    />
  );
}
