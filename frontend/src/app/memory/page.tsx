"use client";

import { useEffect, useState } from "react";
import { ApiError, memoryApi } from "@/lib/api";
import { MEMORY_COLLECTIONS, type MemoryCollection, type MemoryHealth, type RetrievedMemory } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { MemoryCollectionCard } from "@/components/memory/MemoryCollectionCard";
import { MemorySearchForm } from "@/components/memory/MemorySearchForm";
import { MemoryRecordCard } from "@/components/memory/MemoryRecordCard";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { Badge } from "@/components/ui/Badge";
import { Brain } from "lucide-react";

export default function MemoryPage() {
  const [health, setHealth] = useState<MemoryHealth | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [collection, setCollection] = useState<MemoryCollection>("episodic_memory");
  const [items, setItems] = useState<RetrievedMemory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    memoryApi
      .health()
      .then(setHealth)
      .catch((err) => setHealthError(err instanceof ApiError ? err.message : "Failed to load memory health"));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    memoryApi
      .recent(collection, 20)
      .then((res) => {
        if (!cancelled) setItems(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load memory");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [collection]);

  async function handleSearch({ text, ticker }: { text: string; ticker: string }) {
    setLoading(true);
    setError(null);
    try {
      if (!text && !ticker) {
        const res = await memoryApi.recent(collection, 20);
        setItems(res);
        return;
      }
      const res = await memoryApi.search({
        collection,
        text: text || undefined,
        ticker: ticker || undefined,
        top_k: 20,
      });
      setItems(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-xl font-semibold text-text">Memory</h1>
        <p className="mt-1 text-sm text-text-muted">
          RAEM&apos;s ChromaDB episodic memory — regime-tagged retrieval, experience replay, and outcome tracking.
        </p>
      </div>

      {healthError ? (
        <ErrorState title="ChromaDB unreachable" description={healthError} />
      ) : health ? (
        <div className="flex flex-wrap items-center gap-3 text-xs text-text-muted">
          <Badge tone={health.ok ? "buy" : "sell"}>{health.ok ? "Healthy" : "Degraded"}</Badge>
          <span>
            embeddings: <span className="font-mono text-text">{health.embedding_provider}/{health.embedding_model}</span>
          </span>
          <span className="truncate font-mono text-text-faint">{health.path}</span>
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {MEMORY_COLLECTIONS.map((c) => (
          <MemoryCollectionCard
            key={c}
            collection={c}
            count={health?.collections[c] ?? 0}
            active={c === collection}
            onSelect={() => setCollection(c)}
          />
        ))}
      </div>

      <Card>
        <CardHeader title="Browse & search" />
        <MemorySearchForm collection={collection} onSearch={handleSearch} loading={loading} />

        <div className="mt-5 space-y-3">
          {loading ? (
            <LoadingState label="Loading memories…" />
          ) : error ? (
            <ErrorState description={error} onRetry={() => handleSearch({ text: "", ticker: "" })} />
          ) : items.length === 0 ? (
            <EmptyState icon={<Brain className="size-5" />} title="No memories found" description="Try a different search or collection." />
          ) : (
            items.map((item) => (
              <MemoryRecordCard
                key={item.record.memory_id}
                item={item}
                collection={collection}
                onDeleted={(id) => setItems((prev) => prev.filter((i) => i.record.memory_id !== id))}
              />
            ))
          )}
        </div>
      </Card>
    </div>
  );
}
