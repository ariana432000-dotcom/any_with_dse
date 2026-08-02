import type { ReactNode } from "react";
import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "./Button";

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("size-4 animate-spin text-text-muted", className)} />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-bg-raised", className)} />;
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-text-muted">
      <Spinner className="size-6" />
      <p className="text-sm">{label}</p>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  icon,
  action,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border py-14 text-center">
      <div className="mb-1 flex size-10 items-center justify-center rounded-full bg-bg-raised text-text-faint">
        {icon ?? <Inbox className="size-5" />}
      </div>
      <p className="text-sm font-medium text-text">{title}</p>
      {description ? <p className="max-w-sm text-xs text-text-muted">{description}</p> : null}
      {action}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  description,
  onRetry,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-sell/25 bg-sell-soft py-14 text-center">
      <div className="mb-1 flex size-10 items-center justify-center rounded-full bg-sell/15 text-sell">
        <AlertTriangle className="size-5" />
      </div>
      <p className="text-sm font-medium text-text">{title}</p>
      {description ? <p className="max-w-sm text-xs text-text-muted">{description}</p> : null}
      {onRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry} className="mt-2">
          Try again
        </Button>
      ) : null}
    </div>
  );
}
