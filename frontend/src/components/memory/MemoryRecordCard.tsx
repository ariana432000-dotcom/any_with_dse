"use client";

import { useState } from "react";
import { Trash2 } from "lucide-react";
import type { MemoryCollection, RetrievedMemory } from "@/lib/types";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { formatDateTime, truncate } from "@/lib/utils";
import { memoryApi } from "@/lib/api";

export function MemoryRecordCard({
  item,
  collection,
  onDeleted,
}: {
  item: RetrievedMemory;
  collection: MemoryCollection;
  onDeleted: (id: string) => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const r = item.record;

  async function handleDelete() {
    if (!confirm(`Delete this memory (${r.memory_id})? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await memoryApi.delete(collection, r.memory_id);
      onDeleted(r.memory_id);
    } catch {
      setDeleting(false);
    }
  }

  return (
    <Card className="animate-fade-in">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            {r.ticker ? <span className="font-mono text-sm font-semibold text-text">{r.ticker}</span> : null}
            {r.market_regime ? <Badge tone="accent">{r.market_regime}</Badge> : null}
            <Badge tone={r.outcome === "WIN" ? "buy" : r.outcome === "LOSS" ? "sell" : "neutral"}>
              {r.outcome}
            </Badge>
            {item.similarity !== null && item.similarity !== undefined ? (
              <span className="font-mono text-[11px] text-text-faint">
                {Math.round(item.similarity * 100)}% match
              </span>
            ) : null}
          </div>
          <p className="mt-1 text-[11px] text-text-faint">{formatDateTime(r.timestamp)}</p>
        </div>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="shrink-0 text-text-faint hover:text-sell disabled:opacity-40"
          aria-label="Delete memory"
        >
          <Trash2 className="size-3.5" />
        </button>
      </div>

      {r.summary ? <p className="mt-3 text-xs leading-relaxed text-text">{truncate(r.summary, 280)}</p> : null}
      {r.decision ? <p className="mt-2 text-xs text-text-muted">Decision: {r.decision}</p> : null}

      {r.tags.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {r.tags.map((tag) => (
            <span key={tag} className="rounded-full bg-bg-raised px-2 py-0.5 text-[10px] text-text-faint">
              {tag}
            </span>
          ))}
        </div>
      ) : null}
    </Card>
  );
}
