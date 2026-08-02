import { Newspaper } from "lucide-react";
import type { NewsItem } from "@/lib/types";
import { EmptyState } from "@/components/ui/States";

export function NewsList({ items, ticker }: { items: NewsItem[]; ticker?: string }) {
  if (items.length === 0) {
    return (
      <EmptyState
        icon={<Newspaper className="size-5" />}
        title="No recent headlines"
        description={ticker ? `Nothing came back for ${ticker} right now — try again shortly.` : "Nothing to show yet."}
      />
    );
  }

  return (
    <ul className="divide-y divide-border-soft">
      {items.map((item, i) => (
        <li key={`${item.title}-${i}`} className="py-3 first:pt-0 last:pb-0">
          {item.url ? (
            
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm leading-snug text-text hover:text-accent hover:underline"
            >
              {item.title}
            </a>
          ) : (
            <p className="text-sm leading-snug text-text">{item.title}</p>
          )}
          <p className="mt-1 text-xs text-text-faint">{item.source}</p>
        </li>
      ))}
    </ul>
  );
}
