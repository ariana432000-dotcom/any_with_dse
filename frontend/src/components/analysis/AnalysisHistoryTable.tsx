import Link from "next/link";
import type { AnalysisHistoryItem } from "@/lib/types";
import { SignalBadge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/States";
import { formatDateTime } from "@/lib/utils";
import { History } from "lucide-react";

export function AnalysisHistoryTable({ items }: { items: AnalysisHistoryItem[] }) {
  if (items.length === 0) {
    return (
      <EmptyState
        icon={<History className="size-5" />}
        title="No analyses yet"
        description="Run your first analysis above to see it appear here."
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border-soft text-left text-xs uppercase tracking-wider text-text-faint">
            <th className="py-2 pr-4 font-medium">Ticker</th>
            <th className="py-2 pr-4 font-medium">Signal</th>
            <th className="py-2 pr-4 font-medium">Confidence</th>
            <th className="py-2 pr-4 font-medium">Status</th>
            <th className="py-2 pr-0 font-medium">When</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const id = item.analysis_id ?? item._id ?? "";
            const rec = item.recommendation;
            return (
              <tr key={id} className="border-b border-border-soft/60 last:border-0">
                <td className="py-3 pr-4">
                  <Link href={`/analysis/${id}`} className="font-mono text-sm font-semibold text-text hover:text-accent">
                    {item.ticker}
                  </Link>
                </td>
                <td className="py-3 pr-4">
                  <SignalBadge signal={rec?.signal} />
                </td>
                <td className="py-3 pr-4 font-mono text-xs tabular-nums text-text-muted">
                  {rec ? `${Math.round(rec.confidence * 100)}%` : "—"}
                </td>
                <td className="py-3 pr-4 text-xs text-text-muted">{item.status}</td>
                <td className="py-3 pr-0 text-xs text-text-faint">
                  {formatDateTime(item.created_at ?? item.updated_at)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
