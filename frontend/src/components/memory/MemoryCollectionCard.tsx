"use client";

import { Database } from "lucide-react";
import type { MemoryCollection } from "@/lib/types";
import { MEMORY_COLLECTION_DESCRIPTIONS, MEMORY_COLLECTION_LABELS } from "@/lib/constants";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/utils";

export function MemoryCollectionCard({
  collection,
  count,
  active,
  onSelect,
}: {
  collection: MemoryCollection;
  count: number;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button onClick={onSelect} className="text-left">
      <Card
        hoverable
        className={cn("h-full cursor-pointer transition-all", active && "border-accent ring-1 ring-accent")}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex size-8 items-center justify-center rounded-lg bg-accent-soft text-accent-strong">
            <Database className="size-4" />
          </div>
          <span className="font-mono text-lg font-semibold tabular-nums text-text">{count}</span>
        </div>
        <p className="mt-3 text-sm font-medium text-text">{MEMORY_COLLECTION_LABELS[collection]}</p>
        <p className="mt-1 text-xs leading-relaxed text-text-faint">
          {MEMORY_COLLECTION_DESCRIPTIONS[collection]}
        </p>
      </Card>
    </button>
  );
}
