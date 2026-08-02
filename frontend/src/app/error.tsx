"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/ui/States";

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("AInvest UI error:", error);
  }, [error]);

  return (
    <ErrorState
      title="This page hit an unexpected error"
      description={error.message || "Please try again, or check that the backend is running."}
      onRetry={reset}
    />
  );
}
