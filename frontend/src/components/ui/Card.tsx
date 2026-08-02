import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  padded?: boolean;
  hoverable?: boolean;
}

export function Card({ children, className, padded = true, hoverable = false, ...props }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-panel",
        padded && "p-5",
        hoverable && "transition-colors hover:bg-panel-hover",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-4 flex items-start justify-between gap-3", className)}>
      <div>
        <h3 className="text-sm font-semibold tracking-wide text-text">{title}</h3>
        {subtitle ? <p className="mt-1 text-xs text-text-muted">{subtitle}</p> : null}
      </div>
      {action}
    </div>
  );
}
