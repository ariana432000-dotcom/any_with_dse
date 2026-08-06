import type { MacroState } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/States";
import { formatNumber } from "@/lib/utils";
import { Globe2 } from "lucide-react";

const REGIME_TONE: Record<string, "buy" | "sell" | "hold" | "neutral"> = {
  RISK_ON_LOW_VOL: "buy",
  RISK_OFF_HIGH_VOL: "sell",
  RATES_RISING: "hold",
  RATES_FALLING: "hold",
  NEUTRAL_MACRO: "neutral",
};

const REGIME_LABELS: Record<string, string> = {
  RISK_ON_LOW_VOL: "Risk-On · Low Vol",
  RISK_OFF_HIGH_VOL: "Risk-Off · High Vol",
  RATES_RISING: "Rates Rising",
  RATES_FALLING: "Rates Falling",
  NEUTRAL_MACRO: "Neutral",
};

export function MacroRegimePanel({ macro }: { macro: MacroState | null }) {
  if (!macro || !macro.report) {
    return (
      <Card>
        <CardHeader title="Macro Regime" subtitle="Market-wide risk backdrop (VIX · 10Y yield · DXY)." />
        <EmptyState icon={<Globe2 className="size-5" />} title="Not assessed yet" />
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="Macro Regime"
        subtitle="Market-wide risk backdrop — independent of this ticker's own technical regime."
        action={
          <Badge tone={REGIME_TONE[macro.regime] ?? "neutral"}>
            {REGIME_LABELS[macro.regime] ?? (macro.regime || "N/A")}
          </Badge>
        }
      />
      <div className="grid grid-cols-3 gap-3 border-b border-border-soft pb-4">
        <MacroStat label="VIX" value={macro.vix} avg={macro.vix_avg} />
        <MacroStat label="10Y Yield" value={macro.tnx} avg={macro.tnx_avg} suffix="%" />
        <MacroStat label="Dollar Index" value={macro.dxy} avg={macro.dxy_avg} />
      </div>
      <p className="mt-4 text-xs leading-relaxed text-text-muted">{macro.report}</p>
    </Card>
  );
}

function MacroStat({
  label,
  value,
  avg,
  suffix = "",
}: {
  label: string;
  value: number | null;
  avg: number | null;
  suffix?: string;
}) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-text-faint">{label}</p>
      <p className="font-mono text-sm font-medium text-text">
        {value !== null ? `${formatNumber(value)}${suffix}` : "—"}
      </p>
      <p className="font-mono text-[10px] text-text-faint">
        30d avg {avg !== null ? `${formatNumber(avg)}${suffix}` : "—"}
      </p>
    </div>
  );
}
