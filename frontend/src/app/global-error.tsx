"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("AInvest fatal error:", error);
  }, [error]);

  return (
    <html lang="en">
      <body className="flex h-dvh items-center justify-center bg-[#0a0d12] font-sans text-[#e7ecf3]">
        <div className="flex flex-col items-center gap-3 px-6 text-center">
          <p className="text-lg font-semibold">AInvest failed to start</p>
          <p className="max-w-sm text-sm text-[#8a97a8]">
            {error.message || "An unexpected error occurred."}
          </p>
          <button
            onClick={reset}
            className="mt-2 rounded-lg bg-[#5b8cff] px-4 py-2 text-sm font-medium text-white"
          >
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
