"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Menu, Search } from "lucide-react";
import { useHealth } from "@/hooks/useHealth";
import { cn } from "@/lib/utils";

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const { health } = useHealth(30_000);

  function handleSearch(e: FormEvent) {
    e.preventDefault();
    const ticker = query.trim().toUpperCase();
    if (!ticker) return;
    router.push(`/analysis?ticker=${encodeURIComponent(ticker)}`);
    setQuery("");
  }

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border-soft bg-bg/80 px-4 backdrop-blur">
      <button
        onClick={onMenu}
        className="text-text-muted hover:text-text md:hidden"
        aria-label="Open navigation"
      >
        <Menu className="size-5" />
      </button>

      <form onSubmit={handleSearch} className="relative flex-1 max-w-sm">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-text-faint" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Jump to ticker (e.g. AAPL)…"
          className="h-9 w-full rounded-lg border border-border bg-panel pl-9 pr-3 font-mono text-xs uppercase tracking-wide text-text placeholder:text-text-faint placeholder:normal-case focus:border-accent"
        />
      </form>

      <div className="ml-auto hidden items-center gap-2 sm:flex">
        <span
          className={cn(
            "size-1.5 rounded-full",
            health?.ai_configured ? "bg-buy" : "bg-hold animate-pulse-dot",
          )}
        />
        <span className="font-mono text-xs text-text-muted">
          {health ? `${health.ai_provider} · ${health.ai_model}` : "connecting…"}
        </span>
      </div>
    </header>
  );
}
