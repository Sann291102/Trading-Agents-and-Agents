"use client";

import { useMemo } from "react";

import { PIPELINE_ORDER } from "@/lib/orgTopology";
import { useOrgStore } from "@/store/orgStore";
import type { AgentInfo, AgentStatusValue } from "@/types";

import { HudFrame } from "./HudFrame";

const STATUS_DOT: Record<AgentStatusValue, string> = {
  idle: "bg-status-idle",
  executing: "bg-status-executing",
  completed: "bg-status-completed",
  needs_review: "bg-status-needs-review",
};

const STATUS_TEXT: Record<AgentStatusValue, string> = {
  idle: "text-status-idle",
  executing: "text-status-executing",
  completed: "text-status-completed",
  needs_review: "text-status-needs_review",
};

function departmentRank(department: string): number {
  const index = PIPELINE_ORDER.indexOf(department);
  return index === -1 ? PIPELINE_ORDER.length : index;
}

function AgentCard({ agent }: { agent: AgentInfo }) {
  const executing = agent.status === "executing";

  return (
    <HudFrame className="hud-panel shrink-0 px-3 py-2">
      {executing && <div className="hud-scanline" aria-hidden="true" />}
      <div className="flex items-center gap-1.5">
        <span
          className={`h-1.5 w-1.5 shrink-0 rounded-full ${STATUS_DOT[agent.status]} ${
            executing ? "animate-pulse" : ""
          }`}
        />
        <p className="hud-label max-w-[10rem] truncate text-[10px] font-semibold text-text-primary">
          {agent.role}
        </p>
      </div>
      <p className="mt-0.5 truncate text-[10px] text-text-muted">{agent.department}</p>
      <div className="mt-1.5 flex items-center gap-2 text-[10px]">
        <span className={`hud-label font-medium ${STATUS_TEXT[agent.status]}`}>
          {agent.status.replace("_", " ")}
        </span>
        {agent.last_confidence != null && (
          <span className="text-text-muted">conf {agent.last_confidence.toFixed(2)}</span>
        )}
        {agent.last_duration_seconds != null && (
          <span className="text-text-muted">{agent.last_duration_seconds.toFixed(1)}s</span>
        )}
      </div>
    </HudFrame>
  );
}

/**
 * Top row of live agent status cards -- the "specialist roster" cue shared
 * by the JARVIS and Sureflow references (a row of small cards, one per
 * agent, each showing status/role/model-ish metadata). Every field here is
 * the same real `AgentInfo` already driving OrgGraph and StatusBar; this is
 * just a second, glanceable presentation of the identical store state, not
 * a new data source.
 */
export function AgentRosterBar() {
  const agents = useOrgStore((state) => state.agents);

  const roster = useMemo(() => {
    return Object.values(agents).sort((a, b) => {
      const rankDiff = departmentRank(a.department) - departmentRank(b.department);
      return rankDiff !== 0 ? rankDiff : a.role.localeCompare(b.role);
    });
  }, [agents]);

  if (roster.length === 0) return null;

  return (
    <div className="flex items-stretch gap-2 overflow-x-auto pb-1">
      {roster.map((agent) => (
        <AgentCard key={agent.role} agent={agent} />
      ))}
    </div>
  );
}
