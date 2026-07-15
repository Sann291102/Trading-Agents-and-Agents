"use client";

import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";

import { getMemoryEntries, getProject } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import type { MemoryEntry } from "@/types";

/**
 * Organizational-memory detail view for a single past project: everything
 * here is sourced directly from the real `ProjectResponse` shape returned
 * by `GET /projects/:id` (src/types/project.ts) -- research report,
 * business requirements and tech plan -- nothing is invented. Fields that
 * are null on the backend (e.g. a project that never reached the research
 * or product stage) are simply omitted rather than faked.
 */
export function ProjectDetailPanel({
  projectId,
  onClose,
}: {
  projectId: string | null;
  onClose: () => void;
}) {
  const {
    data: project,
    isLoading,
    error,
  } = useQuery({
    queryKey: projectId ? queryKeys.project(projectId) : (["project", "__none__"] as const),
    queryFn: () => getProject(projectId as string),
    enabled: !!projectId,
  });

  // Durable organizational-memory entries the pipeline recorded for this
  // run. The endpoint is list-only, so we fetch recent entries and keep the
  // ones tied to this project (see getMemoryEntries).
  const { data: memoryEntries } = useQuery({
    queryKey: queryKeys.memoryEntries(50),
    queryFn: () => getMemoryEntries(50),
    enabled: !!projectId,
  });
  const projectMemory = (memoryEntries ?? []).filter(
    (entry) => entry.project_id === projectId
  );

  if (!projectId) return null;

  return (
    <aside className="glass-panel fixed right-4 top-4 bottom-4 z-40 w-full max-w-md overflow-y-auto p-5 text-sm">
      <header className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-text-muted">Project memory</p>
          <h2 className="break-words text-base font-semibold text-text-primary">
            {project?.goal ?? "Loading..."}
          </h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close project detail"
          className="shrink-0 rounded border border-border px-2 py-1 text-xs text-text-secondary hover:border-accent-blue hover:text-text-primary"
        >
          Close ✕
        </button>
      </header>

      {isLoading && <p className="text-text-secondary">Loading project detail...</p>}
      {error && (
        <p className="text-status-needs_review">
          Failed to load project: {error instanceof Error ? error.message : "unknown error"}
        </p>
      )}

      {project && (
        <div className="space-y-5">
          <div className="flex flex-wrap gap-2 text-xs">
            <StatusBadge label="Research approved" ok={project.research_approved} />
            <StatusBadge label="Final approved" ok={project.approved} />
          </div>

          {projectMemory.length > 0 && (
            <Section title={`Organizational memory (${projectMemory.length})`}>
              {projectMemory.map((entry) => (
                <MemoryCard key={entry.id} entry={entry} />
              ))}
            </Section>
          )}

          {project.research_report && (
            <Section title="Research report">
              <Field label="Executive summary" value={project.research_report.executive_summary} />
              <Field label="Recommended direction" value={project.research_report.recommended_direction} />
              <ListField label="Opportunities" items={project.research_report.opportunities} />
              <ListField label="Risks" items={project.research_report.risks} />
              <ListField label="Assumptions" items={project.research_report.assumptions} />
              <ListField label="Supporting evidence" items={project.research_report.supporting_evidence} />

              <SubSection title={`Domain knowledge -- ${project.research_report.domain.industry}`}>
                <ListField label="Terminology" items={project.research_report.domain.terminology} />
                <ListField label="Business workflows" items={project.research_report.domain.business_workflows} />
                <ListField label="Compliance concerns" items={project.research_report.domain.compliance_concerns} />
                <ListField label="Industry standards" items={project.research_report.domain.industry_standards} />
                <ListField label="User personas" items={project.research_report.domain.user_personas} />
                <ListField label="Business constraints" items={project.research_report.domain.business_constraints} />
                <ListField label="KPIs" items={project.research_report.domain.kpis} />
                <ListField label="Pain points" items={project.research_report.domain.pain_points} />
                <ListField label="Domain risks" items={project.research_report.domain.domain_risks} />
              </SubSection>

              <SubSection title="Market research">
                <ListField label="Target users" items={project.research_report.market.target_users} />
                <ListField label="Existing products" items={project.research_report.market.existing_products} />
                <Field label="Market size estimate" value={project.research_report.market.market_size_estimate} />
                <Field label="Pricing landscape" value={project.research_report.market.pricing_landscape} />
                <ListField label="Customer expectations" items={project.research_report.market.customer_expectations} />
                <ListField label="Emerging trends" items={project.research_report.market.emerging_trends} />
                <ListField label="Technology adoption" items={project.research_report.market.technology_adoption} />
              </SubSection>

              <SubSection title="Competitor matrix">
                {project.research_report.competitor.competitors.map((competitor) => (
                  <div key={competitor.name} className="mb-2 rounded border border-border/60 p-2">
                    <p className="font-medium text-text-primary">{competitor.name}</p>
                    <Field label="Pricing" value={competitor.pricing} />
                    <Field label="Architecture" value={competitor.architecture} />
                    <Field label="Technology" value={competitor.technology} />
                    <ListField label="Features" items={competitor.features} />
                    <ListField label="Strengths" items={competitor.strengths} />
                    <ListField label="Weaknesses" items={competitor.weaknesses} />
                    <ListField label="Differentiators" items={competitor.differentiators} />
                  </div>
                ))}
                <ListField
                  label="Feature gaps"
                  items={project.research_report.competitor.feature_gaps.map(
                    (gap) =>
                      `${gap.feature} -- us: ${gap.our_status}, them: ${gap.competitor_status}${
                        gap.notes ? ` (${gap.notes})` : ""
                      }`
                  )}
                />
                <ListField label="SWOT -- Strengths" items={project.research_report.competitor.swot.strengths} />
                <ListField label="SWOT -- Weaknesses" items={project.research_report.competitor.swot.weaknesses} />
                <ListField label="SWOT -- Opportunities" items={project.research_report.competitor.swot.opportunities} />
                <ListField label="SWOT -- Threats" items={project.research_report.competitor.swot.threats} />
              </SubSection>

              <SubSection title="Technical research">
                <ListField label="Frameworks" items={project.research_report.technical.frameworks} />
                <ListField label="Cloud services" items={project.research_report.technical.cloud_services} />
                <ListField label="Architecture patterns" items={project.research_report.technical.architecture_patterns} />
                <ListField label="Existing APIs" items={project.research_report.technical.existing_apis} />
                <ListField label="SDKs" items={project.research_report.technical.sdks} />
                <ListField label="Integration possibilities" items={project.research_report.technical.integration_possibilities} />
                <ListField label="Licensing notes" items={project.research_report.technical.licensing_notes} />
                <ListField label="Performance benchmarks" items={project.research_report.technical.performance_benchmarks} />
              </SubSection>
            </Section>
          )}

          {project.research_review && (
            <Section title="Research review notes">
              <p className="whitespace-pre-wrap text-text-secondary">{project.research_review}</p>
            </Section>
          )}

          {project.business_requirements && (
            <Section title="Business requirements">
              <Field label="Vision" value={project.business_requirements.vision.statement} />
              <Field label="Value proposition" value={project.business_requirements.vision.value_proposition} />
              <ListField label="Target users" items={project.business_requirements.vision.target_users} />

              <SubSection title={`Epics (${project.business_requirements.epics.length})`}>
                {project.business_requirements.epics.map((epic) => (
                  <div key={epic.title} className="mb-2 rounded border border-border/60 p-2">
                    <p className="font-medium text-text-primary">{epic.title}</p>
                    <p className="text-text-secondary">{epic.description}</p>
                    {epic.user_stories.length > 0 && (
                      <ul className="mt-1 list-disc space-y-0.5 pl-4">
                        {epic.user_stories.map((story, index) => (
                          <li key={index} className="text-text-secondary">
                            As {story.as_a}, I want {story.i_want}, so that {story.so_that}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </SubSection>

              {project.business_requirements.release_roadmap.length > 0 && (
                <SubSection title="Release roadmap">
                  {project.business_requirements.release_roadmap.map((phase) => (
                    <div key={phase.name} className="mb-1">
                      <p className="font-medium text-text-primary">{phase.name}</p>
                      <p className="text-text-secondary">{phase.scope}</p>
                    </div>
                  ))}
                </SubSection>
              )}

              <ListField label="Sprint suggestions" items={project.business_requirements.sprint_suggestions} />

              {project.business_requirements.risk_register.length > 0 && (
                <SubSection title="Risk register">
                  {project.business_requirements.risk_register.map((risk, index) => (
                    <p key={index} className="text-text-secondary">
                      {risk.description} -- likelihood {risk.likelihood}, impact {risk.impact}. Mitigation:{" "}
                      {risk.mitigation}
                    </p>
                  ))}
                </SubSection>
              )}

              {project.business_requirements.success_metrics.length > 0 && (
                <SubSection title="Success metrics">
                  {project.business_requirements.success_metrics.map((metric, index) => (
                    <p key={index} className="text-text-secondary">
                      {metric.name}: target {metric.target} -- {metric.rationale}
                    </p>
                  ))}
                </SubSection>
              )}
            </Section>
          )}

          {project.tech_plan && (
            <Section title="Tech plan">
              <p className="whitespace-pre-wrap text-text-secondary">{project.tech_plan}</p>
            </Section>
          )}

          {project.review && (
            <Section title="Final review">
              <p className="whitespace-pre-wrap text-text-secondary">{project.review}</p>
            </Section>
          )}
        </div>
      )}
    </aside>
  );
}

const MEMORY_TYPE_LABELS: Record<MemoryEntry["type"], string> = {
  research_finding: "Research finding",
  architectural_decision: "Architectural decision",
  lesson_learned: "Lesson learned",
  reusable_component: "Reusable component",
  risk: "Risk",
};

function MemoryCard({ entry }: { entry: MemoryEntry }) {
  return (
    <div className="rounded border border-border/60 p-2">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="rounded-full border border-accent-blue px-2 py-0.5 text-[10px] uppercase tracking-wide text-accent-blue">
          {MEMORY_TYPE_LABELS[entry.type] ?? entry.type}
        </span>
        <span className="shrink-0 text-[10px] text-text-muted">
          {entry.owner} · confidence {(entry.confidence * 100).toFixed(0)}%
        </span>
      </div>
      <p className="font-medium text-text-primary">{entry.title}</p>
      <p className="whitespace-pre-wrap text-text-secondary">{entry.summary}</p>
    </div>
  );
}

function StatusBadge({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span
      className={`rounded-full border px-2 py-0.5 ${
        ok ? "border-status-completed text-status-completed" : "border-border text-text-muted"
      }`}
    >
      {label}: {ok ? "yes" : "no"}
    </span>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2 border-t border-border pt-3 first:border-t-0 first:pt-0">
      <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
      {children}
    </section>
  );
}

function SubSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="rounded border border-border/60 p-2">
      <summary className="cursor-pointer text-xs font-medium text-text-secondary">{title}</summary>
      <div className="mt-2 space-y-1">{children}</div>
    </details>
  );
}

function Field({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <p className="text-text-secondary">
      <span className="font-medium text-text-primary">{label}: </span>
      {value}
    </p>
  );
}

function ListField({ label, items }: { label: string; items?: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <p className="font-medium text-text-primary">{label}</p>
      <ul className="list-disc space-y-0.5 pl-4">
        {items.map((item, index) => (
          <li key={index} className="text-text-secondary">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
