"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getProject, getProjects } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import { MISSION_STAGES, type MissionStage } from "@/lib/orgTopology";
import { useOrgStore } from "@/store/orgStore";
import type { OrgEvent, ProjectResponse } from "@/types";

import { HudFrame } from "./HudFrame";

const RECENT_PROJECTS_LIMIT = 8;

/**
 * Which MISSION_STAGES ids count as "reached" for the *live* run, driven
 * only by real OrgEvents already sitting in the store -- a stage lights up
 * the moment any of its `eventTypes` has actually been published for this
 * project, nothing inferred beyond that. Unimplemented stages never light
 * up here even if `eventTypes` happens to be non-empty (see `deployment`),
 * because there is no real backend signal behind them yet.
 */
function reachedFromEvents(events: OrgEvent[]): Set<string> {
  const reached = new Set<string>();
  for (const stage of MISSION_STAGES) {
    if (!stage.implemented) continue;
    if (stage.eventTypes.some((type) => events.some((event) => event.type === type))) {
      reached.add(stage.id);
    }
  }
  return reached;
}

/**
 * Historical playback has no live event log to replay (the store's event
 * buffer is capped and scoped to the current session), so reached stages
 * are inferred from the persisted ProjectResponse instead. This is sound
 * because `run_organization` (aio/orchestration/graph.py) only calls
 * `save_project` after the *entire* LangGraph pipeline completes without
 * raising -- an uncaught exception mid-run is never persisted at all -- so
 * any project reachable via `GET /projects/{id}` is itself proof the
 * objective was received, research ran, and the run was written to memory.
 * The graph's one real branch point is the research-review gate
 * (`research_approved`, which the graph deliberately does not loop back
 * on yet -- see that file's docstring), and the Engineering hand-off is
 * evidenced by a non-empty `tech_plan`. Those two are checked explicitly
 * rather than assumed.
 */
function reachedFromProject(project: ProjectResponse): Set<string> {
  const reached = new Set<string>(["objective_received", "memory_update"]);
  if (project.research_report) reached.add("research");
  if (project.research_approved) reached.add("planning");
  if (project.tech_plan.trim().length > 0) reached.add("development");
  return reached;
}

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

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1).trimEnd()}…`;
}

function StageMarker({ stage, reached }: { stage: MissionStage; reached: boolean }) {
  if (!stage.implemented) {
    return (
      <div
        className="flex shrink-0 flex-col items-center gap-1.5"
        title={`${stage.label}: not yet implemented -- no backend department produces this signal yet`}
      >
        <span className="h-2.5 w-2.5 rounded-full border border-border bg-surface-raised opacity-40" />
        <span className="block w-[5.5rem] text-center text-[10px] italic leading-tight text-text-muted/60">
          {stage.label}
        </span>
      </div>
    );
  }

  return (
    <div className="flex shrink-0 flex-col items-center gap-1.5">
      <span
        className={`h-2.5 w-2.5 rounded-full border transition-colors ${
          reached ? "border-accent-cyan bg-accent-cyan" : "border-border bg-surface-raised"
        }`}
        style={reached ? { boxShadow: "var(--glow-cyan)" } : undefined}
      />
      <span
        className={`block w-[5.5rem] text-center text-[10px] leading-tight ${
          reached ? "font-medium text-text-primary" : "text-text-muted"
        }`}
      >
        {stage.label}
      </span>
    </div>
  );
}

/**
 * Horizontal mission timeline. Renders MISSION_STAGES lit up in the order
 * the live run (or a played-back historical run) actually reached them --
 * never faked, never reordered. Doubles as a lightweight playback picker
 * over recent projects so a past mission's shape can be inspected the same
 * way the live one is.
 */
export function MissionTimeline() {
  const events = useOrgStore((state) => state.events);
  const activeProjectId = useOrgStore((state) => state.activeProjectId);

  const [playbackProjectId, setPlaybackProjectId] = useState<string | null>(null);
  const isPlayback = playbackProjectId !== null;

  const recentProjectsQuery = useQuery({
    queryKey: queryKeys.projects(RECENT_PROJECTS_LIMIT),
    queryFn: () => getProjects(RECENT_PROJECTS_LIMIT),
  });

  const playbackProjectQuery = useQuery({
    queryKey: queryKeys.project(playbackProjectId ?? ""),
    queryFn: () => getProject(playbackProjectId as string),
    enabled: isPlayback,
  });

  const liveEvents = useMemo(
    () => (activeProjectId ? events.filter((event) => event.project_id === activeProjectId) : []),
    [events, activeProjectId]
  );

  const reachedIds = useMemo(() => {
    if (isPlayback) {
      return playbackProjectQuery.data
        ? reachedFromProject(playbackProjectQuery.data)
        : new Set<string>();
    }
    return reachedFromEvents(liveEvents);
  }, [isPlayback, playbackProjectQuery.data, liveEvents]);

  const stageReachedFlags = MISSION_STAGES.map(
    (stage) => stage.implemented && reachedIds.has(stage.id)
  );

  // Connecting-line segments light up spanning from one reached stage to
  // the next reached one (skipping over any unreached/unimplemented gaps
  // in between), per the spec's "connecting line to the next reached
  // stage" -- segments before the first or after the last reached stage
  // stay dim.
  const reachedIndices = stageReachedFlags.reduce<number[]>((acc, isReached, i) => {
    if (isReached) acc.push(i);
    return acc;
  }, []);
  const gapLit = new Array(MISSION_STAGES.length - 1).fill(false);
  for (let k = 0; k < reachedIndices.length - 1; k++) {
    for (let g = reachedIndices[k]; g < reachedIndices[k + 1]; g++) gapLit[g] = true;
  }

  const recentProjects = recentProjectsQuery.data ?? [];

  const subtitle = isPlayback
    ? playbackProjectQuery.isLoading
      ? "Loading mission…"
      : playbackProjectQuery.isError || !playbackProjectQuery.data
        ? "Failed to load mission."
        : truncate(playbackProjectQuery.data.goal, 88)
    : activeProjectId
      ? "Live mission in progress"
      : "No active mission yet";

  return (
    <HudFrame className="hud-panel space-y-5 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="hud-label text-xs font-medium text-text-muted">
            Mission Timeline
          </h2>
          <p className="mt-0.5 text-xs text-text-secondary">{subtitle}</p>
        </div>
        {isPlayback && (
          <span className="hud-label shrink-0 text-[10px] text-accent-purple">
            Playback
          </span>
        )}
      </header>

      <div className="flex items-center overflow-x-auto pb-1">
        {MISSION_STAGES.map((stage, i) => (
          <div key={stage.id} className="flex flex-1 items-center last:flex-none">
            <StageMarker stage={stage} reached={stageReachedFlags[i]} />
            {i < MISSION_STAGES.length - 1 && (
              <div
                aria-hidden="true"
                className={`mx-1 h-px flex-1 transition-colors ${
                  gapLit[i] ? "bg-accent-cyan" : "bg-border"
                }`}
              />
            )}
          </div>
        ))}
      </div>

      <div className="space-y-2">
        <h3 className="text-[11px] font-medium uppercase tracking-wide text-text-muted">
          Recent missions
        </h3>
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <button
            type="button"
            onClick={() => setPlaybackProjectId(null)}
            aria-pressed={!isPlayback}
            className={`glass-panel shrink-0 px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent-cyan/50 ${
              !isPlayback
                ? "bg-accent-cyan/10 text-accent-cyan"
                : "text-text-secondary hover:text-text-primary"
            }`}
          >
            Live
          </button>

          {recentProjectsQuery.isLoading && (
            <span className="px-2 text-xs italic text-text-muted">Loading missions…</span>
          )}
          {recentProjectsQuery.isError && (
            <span className="px-2 text-xs text-status-needs_review">
              Failed to load missions.
            </span>
          )}
          {!recentProjectsQuery.isLoading &&
            !recentProjectsQuery.isError &&
            recentProjects.length === 0 && (
              <span className="px-2 text-xs italic text-text-muted">
                No missions recorded yet.
              </span>
            )}

          {recentProjects.map((project) => (
            <button
              key={project.id}
              type="button"
              onClick={() => setPlaybackProjectId(project.id)}
              title={project.goal}
              aria-pressed={playbackProjectId === project.id}
              className={`glass-panel max-w-[16rem] shrink-0 px-3 py-1.5 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent-cyan/50 ${
                playbackProjectId === project.id
                  ? "bg-accent-cyan/10 text-accent-cyan"
                  : "text-text-secondary hover:text-text-primary"
              }`}
            >
              <span className="block truncate font-medium">{truncate(project.goal, 40)}</span>
              <span className="mt-0.5 block text-[10px] text-text-muted">
                {formatRelativeTime(project.created_at)}
              </span>
            </button>
          ))}
        </div>
      </div>
    </HudFrame>
  );
}
