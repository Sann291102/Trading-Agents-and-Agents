"use client";

import { useEffect, useRef, useState } from "react";

import { useOrgStore } from "@/store/orgStore";
import type { EventType, OrgEvent } from "@/types";

import { HudFrame } from "./HudFrame";

const MAX_VISIBLE_LINES = 200;

interface StatusWord {
  label: string;
  colorClass: string;
}

/** Every EventType mapped to a short status word + accent color -- the log
 * line format is `[time] role/department · status · duration · confidence`,
 * never the raw event.message body, per the "agent + status + timing only"
 * log level (see NotificationStack for the richer message-body variant). */
function statusWordFor(event: OrgEvent): StatusWord {
  const failed = Boolean((event.payload as { error?: unknown } | null)?.error);
  const table: Record<EventType, StatusWord> = {
    agent_started: { label: "started", colorClass: "text-status-executing" },
    agent_finished: failed
      ? { label: "failed", colorClass: "text-status-needs_review" }
      : { label: "completed", colorClass: "text-status-completed" },
    task_delegated: { label: "delegated", colorClass: "text-accent-blue" },
    research_complete: { label: "research complete", colorClass: "text-accent-cyan" },
    review_requested: { label: "review requested", colorClass: "text-status-waiting" },
    approval_granted: { label: "approved", colorClass: "text-status-completed" },
    changes_requested: { label: "changes requested", colorClass: "text-status-needs_review" },
    memory_updated: { label: "memory updated", colorClass: "text-accent-cyan" },
    knowledge_added: { label: "knowledge added", colorClass: "text-accent-cyan" },
    deployment_started: { label: "deployment started", colorClass: "text-accent-blue" },
    deployment_finished: { label: "deployment finished", colorClass: "text-status-completed" },
    workflow_failed: { label: "workflow failed", colorClass: "text-status-needs_review" },
  };
  return table[event.type];
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "--:--:--";
  return date.toLocaleTimeString(undefined, { hour12: false });
}

function LogLine({ event }: { event: OrgEvent }) {
  const status = statusWordFor(event);
  const subject = event.agent_role ?? event.department ?? "Organization";

  return (
    <div className="flex items-baseline gap-2 border-b border-border/40 px-3 py-1.5 font-mono text-[11px] leading-tight">
      <span className="shrink-0 text-text-muted">{formatTime(event.timestamp)}</span>
      <span className="min-w-0 flex-1 truncate text-text-primary">{subject}</span>
      <span className={`shrink-0 ${status.colorClass}`}>[{status.label}]</span>
      {event.duration_seconds != null && (
        <span className="shrink-0 text-text-muted">{event.duration_seconds.toFixed(1)}s</span>
      )}
      {event.confidence != null && (
        <span className="shrink-0 text-text-muted">conf {event.confidence.toFixed(2)}</span>
      )}
    </div>
  );
}

/**
 * Live-streaming execution log: one compact line per org event (agent +
 * status + timing, never the raw message body), auto-scrolling as new
 * events land via the existing SSE store (`useOrgEventStream` already feeds
 * `state.events` -- this just renders it). A side panel next to the 3D
 * graph, collapsible to a slim tab so it never has to be the only way to
 * read the mission.
 */
export function ExecutionLogPanel() {
  const events = useOrgStore((state) => state.events);
  const [collapsed, setCollapsed] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  const visible = events.slice(-MAX_VISIBLE_LINES);

  useEffect(() => {
    if (!autoScroll) return;
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [visible.length, autoScroll]);

  function handleScroll() {
    const node = scrollRef.current;
    if (!node) return;
    const atBottom = node.scrollHeight - node.scrollTop - node.clientHeight < 24;
    setAutoScroll(atBottom);
  }

  if (collapsed) {
    return (
      <HudFrame className="hud-panel pointer-events-auto absolute right-4 top-24 z-10">
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          aria-label="Show execution log"
          className="hud-label flex items-center gap-1.5 px-2 py-3 text-[10px] font-medium text-text-secondary transition-colors hover:text-accent-cyan [writing-mode:vertical-rl]"
        >
          System Log
          <span className="h-1.5 w-1.5 rounded-full bg-status-completed" />
        </button>
      </HudFrame>
    );
  }

  return (
    <HudFrame className="hud-panel pointer-events-auto absolute right-4 top-24 bottom-4 z-10 flex w-80 max-w-[calc(100vw-2rem)] flex-col overflow-hidden">
      <div className="hud-scanline" aria-hidden="true" />
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div>
          <p className="hud-label text-[11px] font-semibold text-accent-cyan">
            System Log
          </p>
          <p className="font-mono text-[10px] text-text-muted">
            {events.length} events this session
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          aria-label="Collapse execution log"
          className="rounded p-1 text-text-muted transition-colors hover:text-text-primary"
        >
          ✕
        </button>
      </div>

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto"
      >
        {visible.length === 0 ? (
          <p className="p-3 font-mono text-[11px] text-text-muted">
            <span className="text-accent-cyan">$</span> awaiting agent activity
            <span className="hud-cursor" />
          </p>
        ) : (
          <>
            {visible.map((event) => (
              <LogLine key={event.id} event={event} />
            ))}
            {autoScroll && (
              <div className="flex items-center gap-1 px-3 py-1.5 font-mono text-[11px] text-accent-cyan">
                <span>$</span>
                <span className="hud-cursor" />
              </div>
            )}
          </>
        )}
      </div>

      {!autoScroll && (
        <button
          type="button"
          onClick={() => {
            setAutoScroll(true);
            const node = scrollRef.current;
            if (node) node.scrollTop = node.scrollHeight;
          }}
          className="border-t border-border px-3 py-1.5 text-[11px] font-medium text-accent-cyan transition-colors hover:text-text-primary"
        >
          ↓ Jump to latest
        </button>
      )}
    </HudFrame>
  );
}
