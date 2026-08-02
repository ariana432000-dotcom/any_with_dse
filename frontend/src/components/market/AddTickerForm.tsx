"use client";

import { useState, type FormEvent } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/Button";

export function AddTickerForm({ onAdd }: { onAdd: (ticker: string) => void }) {
  const [value, setValue] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    const t = value.trim().toUpperCase();
    if (!t) return;
    onAdd(t);
    setValue("");
  }

  return (
    <form onSubmit={submit} className="flex items-center gap-2">
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Add ticker (e.g. GOOGL)"
        className="h-9 w-40 rounded-lg border border-border bg-bg-raised px-3 font-mono text-xs uppercase text-text placeholder:text-text-faint placeholder:normal-case focus:border-accent"
        maxLength={10}
      />
      <Button type="submit" size="sm" variant="secondary">
        <Plus className="size-3.5" />
        Add
      </Button>
    </form>
  );
}
