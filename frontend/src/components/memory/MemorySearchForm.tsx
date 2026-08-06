"use client";

import { useState, type FormEvent } from "react";
import { Search } from "lucide-react";
import { Button } from "@/components/ui/Button";
import type { MemoryCollection } from "@/lib/types";

export function MemorySearchForm({
  collection,
  onSearch,
  loading,
}: {
  collection: MemoryCollection;
  onSearch: (params: { text: string; ticker: string }) => void;
  loading: boolean;
}) {
  const [text, setText] = useState("");
  const [ticker, setTicker] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    onSearch({ text: text.trim(), ticker: ticker.trim().toUpperCase() });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
      <div className="relative flex-1">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-text-faint" />
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={`Semantic search in ${collection}…`}
          className="h-9 w-full rounded-lg border border-border bg-bg-raised pl-9 pr-3 text-sm text-text placeholder:text-text-faint focus:border-accent"
        />
      </div>
      <input
        value={ticker}
        onChange={(e) => setTicker(e.target.value)}
        placeholder="Ticker filter"
        className="h-9 w-full rounded-lg border border-border bg-bg-raised px-3 font-mono text-xs uppercase text-text placeholder:text-text-faint placeholder:normal-case focus:border-accent sm:w-32"
        maxLength={10}
      />
      <Button type="submit" size="sm" variant="secondary" loading={loading}>
        Search
      </Button>
    </form>
  );
}
