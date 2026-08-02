import type { BacktestBucket } from "@/lib/types";
import { formatPercent } from "@/lib/utils";

export function BucketTable({ title, buckets }: { title: string; buckets: Record<string, BacktestBucket> }) {
  const entries = Object.entries(buckets).sort((a, b) => b[1].count - a[1].count);

  return (
    <div>
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-text-faint">{title}</p>
      {entries.length === 0 ? (
        <p className="text-xs text-text-faint">No data yet.</p>
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border-soft text-left text-text-faint">
              <th className="py-1.5 pr-2 font-medium">Bucket</th>
              <th className="py-1.5 pr-2 font-medium">N</th>
              <th className="py-1.5 pr-2 font-medium">Win rate</th>
              <th className="py-1.5 pr-0 font-medium">Avg P&amp;L</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([key, b]) => (
              <tr key={key} className="border-b border-border-soft/60 last:border-0">
                <td className="py-1.5 pr-2 font-mono text-text">{key}</td>
                <td className="py-1.5 pr-2 text-text-muted">{b.count}</td>
                <td className="py-1.5 pr-2 text-text-muted">{formatPercent(b.win_rate * 100, 0)}</td>
                <td className={`py-1.5 pr-0 font-mono ${b.avg_pnl_pct >= 0 ? "text-buy" : "text-sell"}`}>
                  {formatPercent(b.avg_pnl_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
