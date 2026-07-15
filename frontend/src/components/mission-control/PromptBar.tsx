"use client";

import { useRef, useState } from "react";

import { createProject } from "@/lib/api";
import { useOrgStore } from "@/store/orgStore";

import { HudFrame } from "./HudFrame";

type SubmitStatus = "idle" | "running" | "error";

/**
 * Persistent goal-input bar, bottom-left of Mission Control -- the always-
 * visible alternative to discovering "Start Project" inside the ⌘K palette.
 * `createProject` only resolves once the whole graph run finishes (a dozen+
 * sequential/parallel LLM calls), so awaiting it directly is exactly the
 * "blocked until done" behavior this needs -- no separate polling required.
 * Live progress in the meantime comes from the already-wired SSE stream
 * (ExecutionLogPanel, MissionTimeline, StatusBar all reflect it independently).
 */
export function PromptBar() {
  const [value, setValue] = useState("");
  const [status, setStatus] = useState<SubmitStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const running = status === "running";

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const goal = value.trim();
    if (!goal || running) return;

    setStatus("running");
    setErrorMessage(null);
    // The backend tears down the previous mission's preview server the
    // moment this new one starts (see PreviewManager) -- clear it here too
    // so PreviewPanel shows "working" instead of a now-dead iframe.
    useOrgStore.getState().setPreview(null, null);

    try {
      const result = await createProject(goal);
      useOrgStore.getState().setPreview(result.preview_url, result.preview_error);
      setValue("");
      setStatus("idle");
    } catch (error) {
      setStatus("error");
      setErrorMessage(error instanceof Error ? error.message : "Failed to start project");
    }
  }

  return (
    <HudFrame className="hud-panel pointer-events-auto absolute bottom-4 left-1/2 z-10 w-[34rem] max-w-[calc(100vw-2rem)] -translate-x-1/2 overflow-hidden">
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
        <button
          type="submit"
          disabled={!value.trim() || running}
          className="hud-label shrink-0 rounded border border-accent-cyan/40 bg-accent-blue/20 px-3 py-2 text-[11px] font-medium text-accent-cyan transition-colors hover:bg-accent-blue/30 disabled:opacity-50"
        >
          {running ? "Working…" : "Start"}
        </button>
      </form>
      {errorMessage && (
        <p className="border-t border-border px-3 py-1.5 text-[11px] text-status-needs_review">
          {errorMessage}
        </p>
      )}
    </HudFrame>
  );
}
