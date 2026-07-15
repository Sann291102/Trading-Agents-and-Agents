"use client";

import dynamic from "next/dynamic";

import { AgentRosterBar } from "@/components/mission-control/AgentRosterBar";
import { ExecutionLogPanel } from "@/components/mission-control/ExecutionLogPanel";
import { HudSidebar } from "@/components/mission-control/HudSidebar";
import { MissionTimeline } from "@/components/mission-control/MissionTimeline";
import { PreviewPanel } from "@/components/mission-control/PreviewPanel";
import { PromptBar } from "@/components/mission-control/PromptBar";
import { useOrgStore } from "@/store/orgStore";

const MissionControlScene = dynamic(
  () => import("@/components/mission-control/MissionControlScene"),
  {
    ssr: false,
    loading: () => (
      <div className="flex flex-1 items-center justify-center text-sm text-text-muted">
        Booting neural core…
      </div>
    ),
  }
);

const CONNECTION_DOT: Record<string, string> = {
  open: "bg-status-completed",
  connecting: "bg-status-executing",
  closed: "bg-status-needs-review",
};

/**
 * Mission Control -- the default landing view. The Executive AI's neural
 * core and the live organization graph fill the whole viewport as a 3D
 * scene; the HUD chrome (sidebar, agent roster, timeline, logs, preview,
 * prompt bar) floats above it. Everything here reacts to real backend
 * state via the global OrgProvider/useOrgStore -- there is no page-local
 * mock data.
 */
export default function Home() {
  const connectionStatus = useOrgStore((state) => state.connectionStatus);
  const activeProjectId = useOrgStore((state) => state.activeProjectId);

  return (
    <main className="relative min-h-0 flex-1">
      <div className="absolute inset-0">
        <MissionControlScene />
      </div>

      {/* Purely decorative technical grid, sitting above the 3D canvas and
       * below every interactive panel -- the "sci-fi HUD" backdrop cue. */}
      <div className="hud-grid-overlay pointer-events-none absolute inset-0 z-[1]" aria-hidden="true" />

      <HudSidebar />

      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 pl-20 pr-4 pt-4 md:pt-6">
        <div className="pointer-events-auto mx-auto flex max-w-4xl flex-col gap-3">
          <div className="hud-panel flex items-center justify-between px-4 py-1.5">
            <p className="hud-label text-[11px] text-text-primary">
              Mission Control
              {activeProjectId && (
                <span className="ml-2 font-mono text-[10px] normal-case tracking-normal text-text-muted">
                  project {activeProjectId}
                </span>
              )}
            </p>
            <span className="flex items-center gap-1.5">
              <span
                className={`h-1.5 w-1.5 rounded-full ${CONNECTION_DOT[connectionStatus]} animate-pulse`}
              />
              <span className="hud-label text-[10px] text-text-muted">{connectionStatus}</span>
            </span>
          </div>

          <AgentRosterBar />
          <MissionTimeline />

          <p className="self-end text-[11px] text-text-muted">
            Press <kbd className="mx-1 rounded border border-border px-1 py-0.5">⌘K</kbd>
            to command the organization
          </p>
        </div>
      </div>

      <ExecutionLogPanel />
      <PreviewPanel />
      <PromptBar />
    </main>
  );
}
