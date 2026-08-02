import { cn, signalTone } from "@/lib/utils";
import type { Signal } from "@/lib/types";

const TONE_COLOR: Record<string, string> = {
  buy: "var(--color-buy)",
  sell: "var(--color-sell)",
  hold: "var(--color-hold)",
  neutral: "var(--color-text-faint)",
};

/**
 * Radial gauge reading a signal's confidence, 0..1. This is AInvest's
 * signature visual — the same reading style is reused for each agent's
 * confidence and for the final portfolio recommendation, so a glance at
 * the ring color/fill tells you BUY/SELL/HOLD and conviction at once.
 */
export function SignalGauge({
  signal,
  confidence,
  size = 72,
  strokeWidth = 6,
  label,
}: {
  signal: Signal | string | null | undefined;
  confidence: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
}) {
  const tone = signalTone(signal);
  const color = TONE_COLOR[tone];
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.min(1, Math.max(0, confidence));
  const dash = circumference * pct;

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-border)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={`${dash} ${circumference}`}
          strokeLinecap="round"
          className="transition-[stroke-dasharray] duration-500 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={cn("font-mono text-sm font-bold tabular-nums")} style={{ color }}>
          {Math.round(pct * 100)}
        </span>
        {label ? <span className="text-[9px] uppercase tracking-wide text-text-faint">{label}</span> : null}
      </div>
    </div>
  );
}
