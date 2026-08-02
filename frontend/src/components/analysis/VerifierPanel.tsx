import type { VerifierState } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge, SignalBadge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/States";
import { ShieldCheck, ShieldAlert, ArrowRight } from "lucide-react";

export function VerifierPanel({ verifier }: { verifier: VerifierState | null }) {
  if (!verifier || !verifier.status) {
    return (
      <Card>
        <CardHeader title="Decision Verifier" subtitle="Post-decision sanity check on the final call." />
        <EmptyState icon={<ShieldCheck className="size-5" />} title="Not verified yet" />
      </Card>
    );
  }

  const flagged = verifier.status === "FLAGGED";

  return (
    <Card>
      <CardHeader
        title="Decision Verifier"
        subtitle="Rule-based + deterministic-numeric + advisory-LLM checks on the final call."
        action={
          <Badge tone={flagged ? "sell" : "buy"}>
            {flagged ? <ShieldAlert className="size-3" /> : <ShieldCheck className="size-3" />}
            {verifier.status}
          </Badge>
        }
      />

      {verifier.auto_overridden ? (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-sell/25 bg-sell-soft p-3">
          <SignalBadge signal={verifier.raw_signal} />
          <ArrowRight className="size-3.5 shrink-0 text-text-faint" />
          <SignalBadge signal={verifier.effective_signal} />
          <p className="text-xs text-sell">
            Auto-overridden to HOLD — raw signal contradicted the Fundamentals Analyst&apos;s own verdict.
          </p>
        </div>
      ) : (
        <div className="mb-4 flex items-center gap-2">
          <span className="text-xs text-text-faint">Actionable signal:</span>
          <SignalBadge signal={verifier.effective_signal} />
        </div>
      )}

      {verifier.notes ? (
        <div className="space-y-2 border-t border-border-soft pt-3">
          {verifier.notes
            .split("\n")
            .filter(Boolean)
            .map((line, i) => (
              <p key={i} className="text-xs leading-relaxed text-text-muted">
                {line}
              </p>
            ))}
        </div>
      ) : null}
    </Card>
  );
}
