"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { getActionRuns, type ActionRun } from "@/lib/api";

const OUTCOME: Record<
  ActionRun["outcome"],
  { label: string; text: string; border: string; dot: string }
> = {
  executed: {
    label: "done",
    text: "text-status-completed",
    border: "border-status-completed/50",
    dot: "bg-status-completed",
  },
  escalated: {
    label: "needs you",
    text: "text-status-executing",
    border: "border-status-executing/50",
    dot: "bg-status-executing",
  },
  failed: {
    label: "failed",
    text: "text-status-needs-review",
    border: "border-status-needs-review/50",
    dot: "bg-status-needs-review",
  },
  rejected: {
    label: "rejected",
    text: "text-text-muted",
    border: "border-border",
    dot: "bg-text-muted",
  },
};

function formatRelativeTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const diffSec = Math.round((Date.now() - date.getTime()) / 1000);
  if (diffSec < 60) return "just now";
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHour = Math.round(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h ago`;
  const diffDay = Math.round(diffHour / 24);
  return `${diffDay}d ago`;
}

/** Hide the empty-params noise ("{}") that most safe actions record. */
function formatParams(paramsJson: string): string {
  const trimmed = paramsJson?.trim() ?? "";
  if (!trimmed || trimmed === "{}" || trimmed === "null") return "";
  try {
    return JSON.stringify(JSON.parse(trimmed), null, 2);
  } catch {
    return trimmed;
  }
}

export interface ActivityFeedProps {
  /** How many runs to pull; the feed shows all of them, newest first. */
  limit?: number;
  className?: string;
}

/**
 * What JARVIS has actually been doing — a chronological stream of executed
 * work, not a dashboard. The backend records every action run (autonomous
 * cycles, approved-then-executed sensitive actions, failures), so this is
 * the founder's evidence that the OS performs rather than describes. Polled
 * rather than pushed: autonomy cycles land between renders and the feed has
 * to feel live without the founder reloading.
 */
export function ActivityFeed({ limit = 40, className = "" }: ActivityFeedProps) {
  const runs = useQuery({
    queryKey: ["action-runs", limit],
    queryFn: () => getActionRuns(limit),
    refetchInterval: 10_000,
  });

  const items = runs.data ?? [];

  return (
    <section className={`hud-panel flex flex-col p-4 ${className}`}>
      <div className="flex items-center justify-between">
        <p className="hud-label text-[11px] text-text-primary">Activity · what JARVIS did</p>
        <span className="hud-label text-[9px] text-text-muted">
          {runs.isFetching ? "syncing…" : items.length > 0 ? `${items.length} actions` : "live"}
        </span>
      </div>

      {runs.isError && (
        <p className="mt-3 text-[12px] text-status-needs-review">
          {runs.error instanceof Error ? runs.error.message : "Could not load the activity feed"}
        </p>
      )}

      {runs.isLoading && <p className="mt-3 text-[12px] text-text-muted">Loading…</p>}

      {!runs.isLoading && !runs.isError && items.length === 0 && (
        <p className="mt-3 text-[12px] leading-relaxed text-text-muted">
          Nothing done yet. JARVIS is at its desk waiting for work — turn on autonomy, or
          just ask for something and it will show up here the moment it&apos;s done.
        </p>
      )}

      {items.length > 0 && (
        <ol className="mt-3 space-y-1.5">
          {items.map((run) => (
            <ActivityEntry key={run.id} run={run} />
          ))}
        </ol>
      )}
    </section>
  );
}

function ActivityEntry({ run }: { run: ActionRun }) {
  const [open, setOpen] = useState(false);
  const outcome = OUTCOME[run.outcome] ?? OUTCOME.rejected;
  const params = formatParams(run.params_json);
  const expandable = Boolean(run.detail || params);

  return (
    <li className={`rounded border bg-surface-raised/60 ${outcome.border}`}>
      <button
        type="button"
        onClick={() => expandable && setOpen((previous) => !previous)}
        aria-expanded={expandable ? open : undefined}
        className={`flex w-full items-start gap-2.5 p-2.5 text-left ${
          expandable ? "cursor-pointer hover:bg-white/5" : "cursor-default"
        }`}
      >
        <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${outcome.dot}`} aria-hidden="true" />
        <span className="min-w-0 flex-1">
          <span className="block text-[13px] leading-snug text-text-primary">{run.summary}</span>
          <span className="mt-0.5 block text-[10px] text-text-muted">
            <span className="font-mono">{run.action}</span>
            {run.actor && <> · {run.actor}</>}
            {" · "}
            <span className={outcome.text}>{outcome.label}</span>
          </span>
        </span>
        <span className="hud-label shrink-0 text-[9px] text-text-muted">
          {formatRelativeTime(run.created_at)}
        </span>
      </button>

      {open && expandable && (
        <div className="border-t border-border px-2.5 py-2">
          {run.detail && (
            <p className="whitespace-pre-wrap text-[11px] leading-relaxed text-text-primary/90">
              {run.detail}
            </p>
          )}
          {params && (
            <pre className="mt-2 overflow-x-auto font-mono text-[10px] leading-relaxed text-text-muted">
              {params}
            </pre>
          )}
        </div>
      )}
    </li>
  );
}
