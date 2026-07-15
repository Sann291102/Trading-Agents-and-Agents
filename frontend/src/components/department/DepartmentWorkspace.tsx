"use client";

import { useMemo } from "react";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { getExecutionLogs, getProject } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import { DEPARTMENTS, departmentsWaitingAfter } from "@/lib/orgTopology";
import { useOrgStore } from "@/store/orgStore";
import type {
  AgentInfo,
  BusinessRequirementsDocument,
  ExecutionLogEntry,
  ProjectResponse,
  ResearchReport,
} from "@/types";

const EXECUTION_LOG_LIMIT = 150;

function formatPercent(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "N/A";
  const pct = value <= 1 ? value * 100 : value;
  return `${Math.round(pct)}%`;
}

function formatDuration(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "N/A";
  return `${value.toFixed(1)}s`;
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function ListBlock({ title, items }: { title: string; items: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <h4 className="text-text-muted uppercase text-xs tracking-wide mb-1">{title}</h4>
      <ul className="list-disc list-inside space-y-0.5 text-text-secondary">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function AgentRosterCard({ agent }: { agent: AgentInfo }) {
  return (
    <div className="glass-panel p-4 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-text-primary text-sm">{agent.role}</span>
        <span
          className={`text-[11px] font-mono uppercase tracking-wide text-status-${agent.status}`}
        >
          {agent.status}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
        <div>
          <div className="text-text-muted">Confidence</div>
          <div>{formatPercent(agent.last_confidence)}</div>
        </div>
        <div>
          <div className="text-text-muted">Duration</div>
          <div>{formatDuration(agent.last_duration_seconds)}</div>
        </div>
      </div>
      {agent.last_message ? (
        <p className="text-xs text-text-secondary line-clamp-3">{agent.last_message}</p>
      ) : (
        <p className="text-xs text-text-muted italic">No messages yet.</p>
      )}
    </div>
  );
}

function ExecutionLogRow({ log }: { log: ExecutionLogEntry }) {
  return (
    <li className="border-b border-border/60 last:border-b-0 py-3 space-y-1 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-text-muted">
        <span>{formatTimestamp(log.started_at)}</span>
        <span>{formatDuration(log.duration_seconds)}</span>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="text-text-secondary font-medium">{log.agent_role}</span>
        <span className="text-text-muted">conf {formatPercent(log.confidence)}</span>
      </div>
      {log.reasoning_summary && <p className="text-text-secondary">{log.reasoning_summary}</p>}
      {log.handoff_target && (
        <p className="text-text-muted">
          Handoff <span aria-hidden="true">-&gt;</span>{" "}
          <span className="text-accent-cyan">{log.handoff_target}</span>
        </p>
      )}
      {log.error && <p className="text-status-needs_review">Error: {log.error}</p>}
    </li>
  );
}

function ResearchArtifact({ report }: { report: ResearchReport }) {
  return (
    <div className="space-y-4 text-sm">
      <div>
        <h4 className="text-text-muted uppercase text-xs tracking-wide mb-1">
          Executive summary
        </h4>
        <p className="text-text-secondary">{report.executive_summary}</p>
      </div>
      <ListBlock title="Opportunities" items={report.opportunities} />
      <ListBlock title="Risks" items={report.risks} />
      <div>
        <h4 className="text-text-muted uppercase text-xs tracking-wide mb-1">
          Recommended direction
        </h4>
        <p className="text-text-secondary">{report.recommended_direction}</p>
      </div>
      <ListBlock title="Assumptions" items={report.assumptions} />
      <ListBlock title="Supporting evidence" items={report.supporting_evidence} />

      <details className="pt-2">
        <summary className="cursor-pointer text-xs text-text-muted uppercase tracking-wide">
          Domain / market / competitor / technical detail
        </summary>
        <div className="mt-3 space-y-4">
          <div>
            <h5 className="text-text-secondary font-medium mb-1 text-xs">
              Domain -- {report.domain.industry || "N/A"}
            </h5>
            <ListBlock title="Pain points" items={report.domain.pain_points} />
            <ListBlock title="Domain risks" items={report.domain.domain_risks} />
          </div>
          <div>
            <h5 className="text-text-secondary font-medium mb-1 text-xs">Market</h5>
            {report.market.market_size_estimate && (
              <p className="text-text-secondary text-xs mb-1">
                {report.market.market_size_estimate}
              </p>
            )}
            <ListBlock title="Emerging trends" items={report.market.emerging_trends} />
          </div>
          <div>
            <h5 className="text-text-secondary font-medium mb-1 text-xs">Competitor SWOT</h5>
            <ListBlock title="Strengths" items={report.competitor.swot.strengths} />
            <ListBlock title="Threats" items={report.competitor.swot.threats} />
          </div>
          <div>
            <h5 className="text-text-secondary font-medium mb-1 text-xs">Technical</h5>
            <ListBlock title="Frameworks" items={report.technical.frameworks} />
            <ListBlock
              title="Architecture patterns"
              items={report.technical.architecture_patterns}
            />
          </div>
        </div>
      </details>
    </div>
  );
}

function ProductArtifact({ brd }: { brd: BusinessRequirementsDocument }) {
  return (
    <div className="space-y-4 text-sm">
      <div>
        <h4 className="text-text-muted uppercase text-xs tracking-wide mb-1">Vision</h4>
        <p className="text-text-secondary">{brd.vision.statement}</p>
        {brd.vision.value_proposition && (
          <p className="text-xs text-text-muted mt-1">{brd.vision.value_proposition}</p>
        )}
      </div>

      <div>
        <h4 className="text-text-muted uppercase text-xs tracking-wide mb-2">
          Epics ({brd.epics.length})
        </h4>
        {brd.epics.length === 0 ? (
          <p className="text-xs text-text-muted italic">None yet.</p>
        ) : (
          <ul className="space-y-2">
            {brd.epics.map((epic, i) => (
              <li key={i} className="border border-border/60 rounded-lg p-2">
                <div className="font-medium text-text-primary text-xs">{epic.title}</div>
                <p className="text-text-secondary text-xs mt-1">{epic.description}</p>
                <div className="text-text-muted text-[11px] mt-1">
                  {epic.user_stories.length} user{" "}
                  {epic.user_stories.length === 1 ? "story" : "stories"}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h4 className="text-text-muted uppercase text-xs tracking-wide mb-2">Risk register</h4>
        {brd.risk_register.length === 0 ? (
          <p className="text-xs text-text-muted italic">None yet.</p>
        ) : (
          <ul className="space-y-1.5">
            {brd.risk_register.map((risk, i) => (
              <li key={i} className="text-xs text-text-secondary">
                <span className="text-status-needs_review font-mono">
                  {risk.likelihood}/{risk.impact}
                </span>{" "}
                -- {risk.description}
                <div className="text-text-muted">Mitigation: {risk.mitigation}</div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h4 className="text-text-muted uppercase text-xs tracking-wide mb-2">Success metrics</h4>
        {brd.success_metrics.length === 0 ? (
          <p className="text-xs text-text-muted italic">None yet.</p>
        ) : (
          <ul className="space-y-1">
            {brd.success_metrics.map((metric, i) => (
              <li key={i} className="text-xs text-text-secondary">
                <span className="text-text-primary">{metric.name}</span>: {metric.target}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function DepartmentArtifact({
  departmentId,
  activeProjectId,
  projectQuery,
}: {
  departmentId: string;
  activeProjectId: string | null;
  projectQuery: UseQueryResult<ProjectResponse>;
}) {
  if (!activeProjectId) {
    return <p className="text-sm text-text-muted italic">No active project yet.</p>;
  }
  if (projectQuery.isLoading) {
    return <p className="text-sm text-text-muted italic">Loading project…</p>;
  }
  if (projectQuery.isError || !projectQuery.data) {
    return <p className="text-sm text-status-needs_review">Failed to load project.</p>;
  }

  const project = projectQuery.data;

  switch (departmentId) {
    case "Research": {
      if (!project.research_report) {
        return (
          <p className="text-sm text-text-muted italic">Research report not yet available.</p>
        );
      }
      return <ResearchArtifact report={project.research_report} />;
    }
    case "Product": {
      if (!project.business_requirements) {
        return (
          <p className="text-sm text-text-muted italic">
            Business requirements not yet available.
          </p>
        );
      }
      return <ProductArtifact brd={project.business_requirements} />;
    }
    case "Engineering": {
      if (!project.tech_plan) {
        return <p className="text-sm text-text-muted italic">Tech plan not yet available.</p>;
      }
      return (
        <pre className="text-xs text-text-secondary whitespace-pre-wrap font-sans">
          {project.tech_plan}
        </pre>
      );
    }
    case "Executive": {
      const hasResearchReview = Boolean(project.research_review);
      const hasReview = Boolean(project.review);
      if (!hasResearchReview && !hasReview) {
        return <p className="text-sm text-text-muted italic">No executive review yet.</p>;
      }
      return (
        <div className="space-y-4 text-sm">
          {hasResearchReview && (
            <div>
              <h4 className="text-text-muted uppercase text-xs tracking-wide mb-1">
                Research review --{" "}
                <span
                  className={
                    project.research_approved ? "text-status-completed" : "text-status-waiting"
                  }
                >
                  {project.research_approved ? "approved" : "pending"}
                </span>
              </h4>
              <p className="text-text-secondary whitespace-pre-wrap">{project.research_review}</p>
            </div>
          )}
          {hasReview && (
            <div>
              <h4 className="text-text-muted uppercase text-xs tracking-wide mb-1">
                Final review --{" "}
                <span
                  className={project.approved ? "text-status-completed" : "text-status-waiting"}
                >
                  {project.approved ? "approved" : "pending"}
                </span>
              </h4>
              <p className="text-text-secondary whitespace-pre-wrap">{project.review}</p>
            </div>
          )}
        </div>
      );
    }
    default:
      return (
        <p className="text-sm text-text-muted italic">No artifact defined for this department.</p>
      );
  }
}

export function DepartmentWorkspace({ departmentId }: { departmentId: string }) {
  const department = DEPARTMENTS.find((d) => d.id === departmentId);

  const agentsRecord = useOrgStore((state) => state.agents);
  const activeProjectId = useOrgStore((state) => state.activeProjectId);
  const activeDepartment = useOrgStore((state) => state.activeDepartment);

  const roster = useMemo(
    () => Object.values(agentsRecord).filter((agent) => agent.department === departmentId),
    [agentsRecord, departmentId]
  );
  const rosterRoles = useMemo(() => new Set(roster.map((agent) => agent.role)), [roster]);

  const waitingDepartments = useMemo(
    () => departmentsWaitingAfter(activeDepartment),
    [activeDepartment]
  );
  const isActiveNow = department !== undefined && activeDepartment === departmentId;
  const isWaiting = department !== undefined && waitingDepartments.has(departmentId);

  const logsQuery = useQuery({
    queryKey: queryKeys.executionLogs(EXECUTION_LOG_LIMIT),
    queryFn: () => getExecutionLogs(EXECUTION_LOG_LIMIT),
  });

  const departmentLogs = useMemo(() => {
    const logs = logsQuery.data ?? [];
    return logs
      .filter((log) => rosterRoles.has(log.agent_role))
      .slice()
      .sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime());
  }, [logsQuery.data, rosterRoles]);

  const projectQuery = useQuery({
    queryKey: queryKeys.project(activeProjectId ?? ""),
    queryFn: () => getProject(activeProjectId as string),
    enabled: Boolean(activeProjectId),
  });

  if (!department) {
    return (
      <div className="glass-panel p-8 text-center">
        <p className="text-lg font-medium text-text-primary">Unknown department</p>
        <p className="text-sm text-text-secondary mt-2">
          &ldquo;{departmentId}&rdquo; does not match any known department.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-xl font-semibold text-text-primary">{department.label}</h2>
          <p className="text-sm text-text-secondary">
            {roster.length} agent{roster.length === 1 ? "" : "s"} · {departmentLogs.length} logged
            execution{departmentLogs.length === 1 ? "" : "s"}
          </p>
        </div>
        <span
          className={`text-xs font-mono uppercase tracking-wide ${
            isActiveNow
              ? "text-status-executing"
              : isWaiting
                ? "text-status-waiting"
                : "text-text-muted"
          }`}
        >
          {isActiveNow ? "Active now" : isWaiting ? "Waiting" : "Idle"}
        </span>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className="space-y-4">
          <h3 className="text-sm font-medium text-text-muted uppercase tracking-wide">
            Agent roster
          </h3>
          {roster.length === 0 ? (
            <div className="glass-panel p-4 text-sm text-text-muted italic">
              No agents reporting for this department yet.
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {roster.map((agent) => (
                <AgentRosterCard key={agent.role} agent={agent} />
              ))}
            </div>
          )}

          <h3 className="text-sm font-medium text-text-muted uppercase tracking-wide pt-2">
            Department artifact
          </h3>
          <div className="glass-panel p-4">
            <DepartmentArtifact
              departmentId={departmentId}
              activeProjectId={activeProjectId}
              projectQuery={projectQuery}
            />
          </div>
        </section>

        <section className="space-y-3">
          <h3 className="text-sm font-medium text-text-muted uppercase tracking-wide">
            Execution log
          </h3>
          <div className="glass-panel p-4 max-h-[36rem] overflow-y-auto">
            {logsQuery.isLoading ? (
              <p className="text-sm text-text-muted italic">Loading execution logs…</p>
            ) : logsQuery.isError ? (
              <p className="text-sm text-status-needs_review">Failed to load execution logs.</p>
            ) : departmentLogs.length === 0 ? (
              <p className="text-sm text-text-muted italic">
                No execution logs for this department yet.
              </p>
            ) : (
              <ul>
                {departmentLogs.map((log) => (
                  <ExecutionLogRow key={log.id} log={log} />
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
