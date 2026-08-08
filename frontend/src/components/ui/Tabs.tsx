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
  variant?: "pill" | "underline" | "numbered";
}) {
  if (variant === "numbered") {
    return (
      <div className="border-b-2 border-hold/60">
        <div className="flex flex-wrap gap-x-1 gap-y-1.5">
          {items.map((t, i) => {
            const isActive = active === t.id;
            return (
              <button
                key={t.id}
                onClick={() => onChange(t.id)}
                className={cn(
                  "flex items-center gap-1.5 rounded-t-md border border-b-0 px-3 py-2 text-xs font-medium transition-colors",
                  isActive
                    ? "border-accent bg-accent text-white"
                    : "border-border-soft bg-panel text-text-muted hover:bg-panel-hover hover:text-text",
                  t.done === false && !isActive && "opacity-50",
                )}
              >
                <span
                  className={cn(
                    "font-mono text-[11px] font-semibold",
                    isActive ? "text-white/80" : "text-hold",
                  )}
                >
                  {i + 1}
                </span>
                {t.label}
                {t.badge}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

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
