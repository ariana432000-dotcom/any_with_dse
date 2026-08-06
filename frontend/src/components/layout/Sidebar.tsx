"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Brain,
  ClipboardCheck,
  Database,
<<<<<<< HEAD
  FileText,
=======
>>>>>>> ade75414b6567b17d70c76d7f1b7d5363ff039b5
  LayoutDashboard,
  LineChart,
  type LucideIcon,
  Moon,
  Newspaper,
  Settings,
  Star,
  Sun,
  Wallet,
  X,
} from "lucide-react";
import { APP_NAME, NAV_ITEMS, type NavItem } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { useTheme } from "@/components/providers/ThemeProvider";
import { ConnectionDot } from "./ConnectionDot";

const ICONS: Record<NavItem["icon"], LucideIcon> = {
  dashboard: LayoutDashboard,
  analysis: LineChart,
  watchlist: Star,
  news: Newspaper,
  memory: Brain,
  dataset: Database,
  backtest: BarChart3,
  "paper-trading": Wallet,
  "fundamentals-check": ClipboardCheck,
<<<<<<< HEAD
  reports: FileText,
=======
>>>>>>> ade75414b6567b17d70c76d7f1b7d5363ff039b5
  settings: Settings,
};

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { theme, toggle } = useTheme();

  return (
    <div className="flex h-full flex-col bg-bg-raised">
      <div className="flex items-center gap-2.5 border-b border-border-soft px-5 py-5">
        <div className="flex size-8 items-center justify-center rounded-lg bg-accent font-mono text-sm font-bold text-white">
          AI
        </div>
        <div>
          <p className="font-display text-sm font-semibold leading-tight text-text">{APP_NAME}</p>
          <p className="text-[11px] leading-tight text-text-faint">Trading Research Terminal</p>
        </div>
        <button
          onClick={onNavigate}
          className="ml-auto text-text-faint hover:text-text md:hidden"
          aria-label="Close navigation"
        >
          <X className="size-5" />
        </button>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
        {NAV_ITEMS.map((item) => {
          const Icon = ICONS[item.icon];
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-accent-soft text-accent-strong"
                  : "text-text-muted hover:bg-panel-hover hover:text-text",
              )}
            >
              <Icon className="size-4 shrink-0" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="space-y-3 border-t border-border-soft px-4 py-4">
        <div className="flex items-center justify-between rounded-lg bg-panel px-3 py-2">
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <ConnectionDot />
            Backend
          </div>
          <button
            onClick={toggle}
            aria-label="Toggle theme"
            className="flex size-6 items-center justify-center rounded-md text-text-faint hover:bg-panel-hover hover:text-text"
          >
            {theme === "dark" ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
          </button>
        </div>
        <p className="px-1 text-[10px] leading-relaxed text-text-faint">
          Local-only. No cloud AI required. Single user, no login.
        </p>
      </div>
    </div>
  );
}
