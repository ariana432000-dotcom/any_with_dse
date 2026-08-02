import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { Signal } from "@/lib/types";
import { signalTone } from "@/lib/utils";

type Tone = "neutral" | "buy" | "sell" | "hold" | "accent";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-bg-raised text-text-muted border-border",
  buy: "bg-buy-soft text-buy border-buy/30",
  sell: "bg-sell-soft text-sell border-sell/30",
  hold: "bg-hold-soft text-hold border-hold/30",
  accent: "bg-accent-soft text-accent-strong border-accent/30",
};

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        TONE_CLASSES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function SignalBadge({ signal, className }: { signal: Signal | string | null | undefined; className?: string }) {
  const tone = signalTone(signal);
  const toneMap: Record<string, Tone> = { buy: "buy", sell: "sell", hold: "hold", neutral: "neutral" };
  return (
    <Badge tone={toneMap[tone]} className={cn("font-mono uppercase", className)}>
      <span
        className={cn(
          "size-1.5 rounded-full",
          tone === "buy" && "bg-buy",
          tone === "sell" && "bg-sell",
          tone === "hold" && "bg-hold",
          tone === "neutral" && "bg-text-faint",
        )}
      />
      {signal || "N/A"}
    </Badge>
  );
}
