"use client";

import gsap from "gsap";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { cancelProject, getProject, startProject } from "@/lib/api";
import { prefersReducedMotion } from "@/lib/motion";
import { queryKeys } from "@/lib/queryClient";
import { useOrgStore } from "@/store/orgStore";

import { HudFrame } from "./HudFrame";

const POLL_MS = 2000;

/**
 * Persistent goal-input bar, bottom-center of Mission Control -- the always-
 * visible alternative to discovering "Start Project" inside the ⌘K palette.
 *
 * `startProject` now returns as soon as the backend has kicked the mission
 * off on a background thread (see api/main.py), not once the whole graph
 * run finishes -- a real run is a dozen+ sequential/parallel LLM calls, too
 * long to hold a request open for. `running`/`errorMessage` are therefore
 * computed at render time from two real signals rather than stored as
 * separate state kept in sync via effects: (1) `GET /projects/{id}`
 * succeeding -- the authoritative "has this persisted yet" signal
 * `run_organization` writes at the very end -- and (2) a
 * `workflow_failed`/`workflow_cancelled` SSE event tagged with this
 * project_id, for runs that stop early and never persist.
 */
export function PromptBar() {
  const [value, setValue] = useState("");
  const [runningProjectId, setRunningProjectId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);

  const events = useOrgStore((state) => state.events);

  const terminalEvent = runningProjectId
    ? events.find(
        (event) =>
          event.project_id === runningProjectId &&
          (event.type === "workflow_failed" || event.type === "workflow_cancelled")
      )
    : undefined;

  const pollQuery = useQuery({
    queryKey: queryKeys.project(runningProjectId ?? ""),
    queryFn: () => getProject(runningProjectId as string),
    enabled: Boolean(runningProjectId) && !terminalEvent,
    refetchInterval: (query) => (query.state.data ? false : POLL_MS),
    retry: false,
  });

  const running = Boolean(runningProjectId) && !terminalEvent && !pollQuery.data;
  const errorMessage =
    terminalEvent?.type === "workflow_failed" ? terminalEvent.message : submitError;

  // A pulse of cyan glow the instant JARVIS picks up a mission -- the state
  // transition an operator most needs to *feel*, not just read in the input
  // becoming disabled. Fires once per `running` flip, not on every render.
  useEffect(() => {
    const node = frameRef.current;
    if (!node || !running || prefersReducedMotion()) return;
    gsap.fromTo(
      node,
      { boxShadow: "0 0 0 0 rgba(34, 211, 238, 0.6)" },
      { boxShadow: "0 0 0 10px rgba(34, 211, 238, 0)", duration: 0.6, ease: "power2.out" }
    );
  }, [running]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const goal = value.trim();
    if (!goal || running) return;

    setSubmitError(null);
    // The backend tears down the previous mission's preview server the
    // moment this new one starts (see PreviewManager) -- clear it here too
    // so PreviewPanel shows "working" instead of a now-dead iframe.
    useOrgStore.getState().setPreview(null, null);

    try {
      const result = await startProject(goal);
      setRunningProjectId(result.project_id);
      setValue("");
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Failed to start project");
    }
  }

  async function handleCancel() {
    if (!runningProjectId) return;
    try {
      await cancelProject(runningProjectId);
    } catch (error) {
      // Best-effort: if the mission already finished (404) or the request
      // otherwise fails, `terminalEvent`/`pollQuery` above still resolve
      // `running` to false once the mission's own terminal signal arrives.
      console.error("cancelProject failed", error);
    }
  }

  return (
    <HudFrame
      ref={frameRef}
      className="hud-panel pointer-events-auto absolute bottom-4 left-1/2 z-10 w-[34rem] max-w-[calc(100vw-2rem)] -translate-x-1/2 overflow-hidden"
    >
      {running && <div className="hud-scanline" aria-hidden="true" />}
      <form onSubmit={handleSubmit} className="flex items-center gap-2 p-2">
        <span className="hud-label shrink-0 pl-1 text-sm text-accent-cyan" aria-hidden="true">
          &gt;
        </span>
        <input
          ref={inputRef}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          disabled={running}
          placeholder="Type a command — describe what to build..."
          aria-label="Mission prompt"
          className="min-w-0 flex-1 bg-transparent font-mono text-sm text-text-primary placeholder:text-text-muted outline-none disabled:opacity-50"
        />
        {running && (
          <span className="hud-waveform flex shrink-0 items-end gap-[3px] px-1" aria-hidden="true">
            {[0, 1, 2, 3, 4].map((bar) => (
              <span key={bar} className="h-3" style={{ animationDelay: `${bar * 0.12}s` }} />
            ))}
          </span>
        )}
        {running ? (
          <button
            type="button"
            onClick={handleCancel}
            className="hud-label shrink-0 rounded border border-status-needs-review/50 bg-status-needs-review/10 px-3 py-2 text-[11px] font-medium text-status-needs_review transition-colors hover:bg-status-needs-review/20"
          >
            Stop
          </button>
        ) : (
          <button
            type="submit"
            disabled={!value.trim()}
            className="hud-label shrink-0 rounded border border-accent-cyan/40 bg-accent-blue/20 px-3 py-2 text-[11px] font-medium text-accent-cyan transition-colors hover:bg-accent-blue/30 disabled:opacity-50"
          >
            Start
          </button>
        )}
      </form>
      {errorMessage && (
        <p className="border-t border-border px-3 py-1.5 text-[11px] text-status-needs_review">
          {errorMessage}
        </p>
      )}
    </HudFrame>
  );
}
