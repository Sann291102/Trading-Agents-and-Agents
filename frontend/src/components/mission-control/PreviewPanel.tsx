"use client";

import { useOrgStore } from "@/store/orgStore";

import { HudFrame } from "./HudFrame";

/**
 * Live preview of the app the organization just built -- an iframe pointed
 * at the local dev server `PreviewManager` started for the mission that
 * just finished. Mirrors ExecutionLogPanel's positioning on the opposite
 * (left) side. Gated on `previewBuilding` (true strictly between the
 * backend's `deployment_started`/`deployment_finished` events for this
 * stage specifically) rather than "any agent executing" -- the latter is
 * true for nearly the entire mission (research, product, backend, swarm),
 * so it would show "Building your preview…" long before the preview stage
 * actually starts. Renders nothing until the mission reaches that stage or
 * a previous mission has already produced a result, so it doesn't occupy
 * space before there's anything preview-relevant to show.
 */
export function PreviewPanel() {
  const previewUrl = useOrgStore((state) => state.previewUrl);
  const previewError = useOrgStore((state) => state.previewError);
  const previewBuilding = useOrgStore((state) => state.previewBuilding);

  if (!previewBuilding && !previewUrl && !previewError) return null;

  return (
    <HudFrame className="hud-panel pointer-events-auto absolute left-20 top-24 bottom-24 z-10 flex w-[28rem] max-w-[calc(100vw-6rem)] flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <p className="hud-label text-[11px] font-semibold text-accent-cyan">
          Live Preview
        </p>
        {previewUrl && !previewBuilding && (
          <a
            href={previewUrl}
            target="_blank"
            rel="noreferrer"
            className="text-[11px] text-text-muted transition-colors hover:text-text-primary"
          >
            Open in new tab ↗
          </a>
        )}
      </div>

      <div className="flex-1 overflow-hidden">
        {previewBuilding ? (
          <div className="flex h-full items-center justify-center gap-2 text-sm text-text-muted">
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-text-muted/40 border-t-text-muted" />
            Building your preview…
          </div>
        ) : previewUrl ? (
          <iframe
            src={previewUrl}
            title="Live preview"
            className="h-full w-full border-0 bg-white"
          />
        ) : previewError ? (
          <p className="whitespace-pre-wrap p-3 text-[12px] text-status-needs_review">
            {previewError}
          </p>
        ) : null}
      </div>
    </HudFrame>
  );
}
