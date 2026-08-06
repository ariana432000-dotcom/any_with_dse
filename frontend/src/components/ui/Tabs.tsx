"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface TabItem {
  id: string;
  label: string;
  done?: boolean;
  badge?: ReactNode;
}

export function Tabs({
  items,
  active,
  onChange,
  variant = "pill",
}: {
  items: TabItem[];
  active: string;
  onChange: (id: string) => void;
  variant?: "pill" | "underline";
}) {
  if (variant === "underline") {
    return (
      <div className="flex flex-wrap gap-1 border-b border-border-soft">
        {items.map((t) => (
          <button
            key={t.id}
            onClick={() => onChange(t.id)}
            className={cn(
              "flex items-center gap-1.5 border-b-2 px-3 py-2 text-xs font-medium transition-colors",
              active === t.id
                ? "border-accent text-text"
                : "border-transparent text-text-faint hover:text-text-muted",
              t.done === false && "opacity-50",
            )}
          >
            {t.label}
            {t.badge}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={cn(
            "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
            active === t.id
              ? "border-accent bg-accent-soft text-accent-strong"
              : "border-border-soft bg-bg-raised text-text-faint hover:text-text-muted",
            t.done === false && "opacity-50",
          )}
        >
          <span
            className={cn(
              "size-1.5 rounded-full",
              t.done === false ? "bg-text-faint" : active === t.id ? "bg-accent" : "bg-buy",
            )}
          />
          {t.label}
          {t.badge}
        </button>
      ))}
    </div>
  );
}
