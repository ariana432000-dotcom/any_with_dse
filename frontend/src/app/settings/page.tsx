"use client";

import { Moon, Sun } from "lucide-react";
import { useHealth } from "@/hooks/useHealth";
import { useTheme } from "@/components/providers/ThemeProvider";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { API_BASE_URL } from "@/lib/api";

export default function SettingsPage() {
  const { health, loading, error, refresh } = useHealth(0);
  const { theme, setTheme } = useTheme();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-xl font-semibold text-text">Settings</h1>
        <p className="mt-1 text-sm text-text-muted">Local configuration and backend status. Single local user — no accounts.</p>
      </div>

      <Card>
        <CardHeader title="Appearance" subtitle="Applies immediately, saved in your browser." />
        <div className="flex gap-2">
          <Button
            variant={theme === "dark" ? "primary" : "secondary"}
            size="sm"
            onClick={() => setTheme("dark")}
          >
            <Moon className="size-3.5" />
            Dark
          </Button>
          <Button
            variant={theme === "light" ? "primary" : "secondary"}
            size="sm"
            onClick={() => setTheme("light")}
          >
            <Sun className="size-3.5" />
            Light
          </Button>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Backend connection"
          subtitle={<span className="font-mono">{API_BASE_URL}</span>}
          action={
            <Button variant="secondary" size="sm" onClick={refresh}>
              Refresh
            </Button>
          }
        />
        {loading ? (
          <LoadingState label="Checking backend…" />
        ) : error ? (
          <ErrorState
            title="Backend unreachable"
            description={`${error} — set NEXT_PUBLIC_API_URL in .env.local if your backend runs elsewhere.`}
            onRetry={refresh}
          />
        ) : health ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <ServiceRow label="Overall" ok={health.status === "ok"} detail={health.status} />
              <ServiceRow label="MongoDB" ok={health.services.mongo} />
              <ServiceRow label="Redis" ok={health.services.redis} />
              <ServiceRow label="ChromaDB" ok={health.services.chroma.ok} detail={health.services.chroma.embedding_provider} />
            </div>
          </div>
        ) : null}
      </Card>

      <Card>
        <CardHeader title="AI engine" subtitle="TradingAgents is the only AI engine — configured via the backend's .env." />
        {health ? (
          <div className="flex flex-wrap items-center gap-3">
            <Badge tone={health.ai_configured ? "buy" : "hold"}>
              {health.ai_configured ? "Configured" : "Needs setup"}
            </Badge>
            <span className="font-mono text-sm text-text">{health.ai_provider}</span>
            <span className="font-mono text-xs text-text-muted">{health.ai_model}</span>
          </div>
        ) : (
          <p className="text-xs text-text-faint">Waiting for backend…</p>
        )}
        <p className="mt-3 text-xs leading-relaxed text-text-muted">
          To change providers or models, edit <code className="rounded bg-bg-raised px-1 py-0.5 font-mono">RAEM_LLM_PROVIDER</code> /{" "}
          <code className="rounded bg-bg-raised px-1 py-0.5 font-mono">RAEM_LLM_MODEL</code> in the backend&apos;s{" "}
          <code className="rounded bg-bg-raised px-1 py-0.5 font-mono">.env</code> and restart the backend. Local Ollama
          models (qwen2.5, llama3.1, mistral, phi4, deepseek-r1) need no API key.
        </p>
      </Card>

      <Card>
        <CardHeader title="About" />
        <p className="text-xs leading-relaxed text-text-muted">
          AInvest is a fully local AI trading research platform — TradingAgents multi-agent analysis, RAEM
          episodic memory in ChromaDB, and MongoDB history, all running on your own machine. No login, no cloud
          AI required, no data leaves your network unless you configure a cloud provider.
        </p>
      </Card>
    </div>
  );
}

function ServiceRow({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border-soft bg-bg-raised px-3 py-2">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="flex items-center gap-1.5">
        <span className={`size-1.5 rounded-full ${ok ? "bg-buy" : "bg-sell"}`} />
        <span className="font-mono text-[11px] text-text-faint">{detail ?? (ok ? "ok" : "down")}</span>
      </span>
    </div>
  );
}
