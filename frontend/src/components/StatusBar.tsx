"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getHealth, getProjects } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import { useOrgStore } from "@/store/orgStore";

const POLL_MS = 15_000;

/**
 * Persistent footer of real organizational metrics. Two items the product
 * spec lists -- CPU usage and queued-workflow count -- are deliberately
 * omitted rather than faked: this backend has no CPU metrics endpoint and
 * no request queue (FastAPI's thread pool has no depth this app exposes),
 * so showing a number for either would be exactly the "static card with
 * fake numbers" the design brief prohibits. Everything shown here is
 * either live store state or a real, measured API round-trip.
 */
export function StatusBar() {
  const agents = useOrgStore((state) => state.agents);
  const connectionStatus = useOrgStore((state) => state.connectionStatus);
  const activeDepartment = useOrgStore((state) => state.activeDepartment);
  const events = useOrgStore((state) => state.events);

  const [latencyMs, setLatencyMs] = useState<number | null>(null);

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const start = performance.now();
      const result = await getHealth();
      setLatencyMs(Math.round(performance.now() - start));
      return result;
    },
    refetchInterval: POLL_MS,
  });

  const projectsQuery = useQuery({
    queryKey: queryKeys.projects(1000),
    queryFn: () => getProjects(1000),
    refetchInterval: POLL_MS,
  });

  const roster = Object.values(agents);
  const executingCount = roster.filter((a) => a.status === "executing").length;
  const confidences = roster
    .map((a) => a.last_confidence)
    .filter((c): c is number => c != null);
  const averageConfidence =
    confidences.length > 0
      ? confidences.reduce((sum, c) => sum + c, 0) / confidences.length
      : null;

  const knowledgeAddedThisSession = events.filter((e) => e.type === "knowledge_added").length;
  const orgState = executingCount > 0 ? (activeDepartment ?? "Working") : "Idle";

  const connectionLabel =
    connectionStatus === "open"
      ? "Live"
      : connectionStatus === "connecting"
        ? "Connecting"
        : "Disconnected";
  const connectionColorClass =
    connectionStatus === "open"
      ? "text-status-completed"
      : connectionStatus === "connecting"
        ? "text-status-executing"
        : "text-status-needs_review";

  return (
    <footer className="hud-panel sticky bottom-0 z-30 flex flex-wrap items-center gap-x-6 gap-y-1 px-4 py-2 font-mono text-[11px] text-text-secondary">
      <Stat label="Agents" value={`${roster.length}`} hint={roster.length ? `${executingCount} active` : undefined} />
      <Stat label="State" value={orgState} />
      <Stat
        label="Avg confidence"
        value={averageConfidence != null ? averageConfidence.toFixed(2) : "—"}
      />
      <Stat
        label="Memory"
        value={projectsQuery.data ? `${projectsQuery.data.length} projects` : "…"}
      />
      <Stat label="Knowledge" value={`+${knowledgeAddedThisSession} this session`} />
      <Stat label="API latency" value={latencyMs != null ? `${latencyMs}ms` : "…"} />
      <Stat
        label="Model"
        value={healthQuery.data ? `${healthQuery.data.llm_provider}/${healthQuery.data.model}` : "…"}
      />

      <span className={`ml-auto flex items-center gap-1.5 font-medium ${connectionColorClass}`}>
        <span className="h-1.5 w-1.5 rounded-full bg-current" />
        <span className="hud-label">{connectionLabel}</span>
      </span>
    </footer>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <span className="flex items-baseline gap-1.5">
      <span className="hud-label text-text-muted">{label}</span>
      <span className="font-medium text-text-primary">{value}</span>
      {hint && <span className="text-text-muted">({hint})</span>}
    </span>
  );
}
