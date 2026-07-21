"use client";

import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { HudSidebar } from "@/components/mission-control/HudSidebar";
import { VoiceAssistantBar } from "@/components/executive/VoiceAssistantBar";
import { ActivityFeed } from "@/components/executive/ActivityFeed";
import { AutonomyControl } from "@/components/executive/AutonomyControl";
import {
  decideApproval,
  generateBriefing,
  generateLaunchPlan,
  getApprovals,
  getCompanies,
  getCompanyMetrics,
  getMilestones,
  isPreRevenue,
  setMilestoneStatus,
  type BusinessMetricSnapshot,
  type Company,
  type ExecutiveBriefing,
  type Milestone,
  type MilestoneStatus,
} from "@/lib/api";

const HEALTH_COLOR: Record<string, string> = {
  strong: "text-status-completed",
  stable: "text-accent-cyan",
  warning: "text-status-executing",
  critical: "text-status-needs-review",
};

const IMPACT_COLOR: Record<string, string> = {
  high: "border-status-needs-review/60 text-status-needs-review",
  medium: "border-status-executing/60 text-status-executing",
  low: "border-border text-text-muted",
};

const SEVERITY_COLOR: Record<string, string> = {
  critical: "text-status-needs-review",
  high: "text-status-needs-review",
  medium: "text-status-executing",
  low: "text-text-muted",
};

function money(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(1)}k`;
  return `$${value.toFixed(0)}`;
}

/**
 * Executive Dashboard -- the default landing view. JARVIS is the founder's
 * business operating system: this page shows business health, revenue,
 * customers, approvals, and today's priorities across every connected
 * company (TradeW first), with the voice assistant as the primary way in.
 * The engineering Mission Control moved to /missions.
 */
export default function ExecutiveDashboard() {
  return (
    <main className="relative min-h-0 flex-1 overflow-y-auto">
      <div className="hud-grid-overlay pointer-events-none absolute inset-0 z-[1]" aria-hidden="true" />
      <HudSidebar />

      <div className="relative z-10 mx-auto flex max-w-6xl flex-col gap-4 py-6 pl-24 pr-6">
        <header className="flex items-end justify-between">
          <div>
            <h1 className="text-lg font-semibold text-text-primary">Executive Dashboard</h1>
            <p className="text-[12px] text-text-muted">
              Your companies, operated by JARVIS. Speak or type below.
            </p>
          </div>
        </header>

        <VoiceAssistantBar />

        {/* What JARVIS is actually doing comes right after the voice bar --
            this is the proof that speaking to it performs work, not just a
            reply. Autonomy sits beside the decisions still waiting on the
            founder, since both are about how much authority JARVIS holds. */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ActivityFeed />
          <AutonomyControl />
        </div>

        <BriefingPanel />

        <CompaniesSection />

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ApprovalsPanel />
          <NotificationsHint />
        </div>
      </div>
    </main>
  );
}

function BriefingPanel() {
  const [briefing, setBriefing] = useState<ExecutiveBriefing | null>(null);
  const generate = useMutation({
    mutationFn: generateBriefing,
    onSuccess: setBriefing,
  });

  return (
    <section className="hud-panel p-4">
      <div className="flex items-center justify-between">
        <p className="hud-label text-[11px] text-text-primary">Executive Briefing · Chief of Staff</p>
        <button
          type="button"
          onClick={() => generate.mutate()}
          disabled={generate.isPending}
          className="rounded border border-accent-cyan/50 px-3 py-1.5 text-[12px] text-accent-cyan transition-colors hover:bg-accent-cyan/10 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {generate.isPending ? "Composing…" : briefing ? "Refresh briefing" : "Generate today's briefing"}
        </button>
      </div>

      {generate.isError && (
        <p className="mt-3 text-[12px] text-status-needs-review">
          {generate.error instanceof Error ? generate.error.message : "Briefing failed"}
        </p>
      )}

      {briefing ? (
        <div className="mt-3 flex flex-col gap-3">
          <div className="flex items-baseline gap-3">
            <span className={`hud-label text-[10px] ${HEALTH_COLOR[briefing.business_health]}`}>
              {briefing.business_health.toUpperCase()}
            </span>
            <h2 className="text-[15px] font-medium text-text-primary">{briefing.headline}</h2>
          </div>
          <p className="text-[13px] leading-relaxed text-text-primary/90">{briefing.summary}</p>

          {briefing.priorities.length > 0 && (
            <div>
              <p className="hud-label mb-2 text-[10px] text-text-muted">Today&apos;s priorities</p>
              <ul className="space-y-2">
                {briefing.priorities.map((priority, index) => (
                  <li key={index} className="flex items-start gap-2 text-[12px]">
                    <span
                      className={`mt-0.5 shrink-0 rounded border px-1.5 py-0.5 text-[9px] uppercase ${IMPACT_COLOR[priority.impact]}`}
                    >
                      {priority.impact}
                    </span>
                    <span className="text-text-primary">
                      {priority.title}
                      <span className="text-text-muted"> — {priority.why_now} · </span>
                      <span className="text-accent-cyan">{priority.owner_agent}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {briefing.risks.length > 0 && (
              <div>
                <p className="hud-label mb-2 text-[10px] text-text-muted">Risks</p>
                <ul className="space-y-1.5">
                  {briefing.risks.map((risk, index) => (
                    <li key={index} className="text-[12px]">
                      <span className={SEVERITY_COLOR[risk.severity]}>▲ {risk.title}</span>
                      {risk.mitigation && (
                        <span className="text-text-muted"> — {risk.mitigation}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {briefing.opportunities.length > 0 && (
              <div>
                <p className="hud-label mb-2 text-[10px] text-text-muted">Opportunities</p>
                <ul className="space-y-1.5">
                  {briefing.opportunities.map((opportunity, index) => (
                    <li key={index} className="text-[12px] text-status-completed">
                      ↗ <span className="text-text-primary">{opportunity}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      ) : (
        !generate.isPending && (
          <p className="mt-3 text-[12px] text-text-muted">
            The Chief of Staff reads where each company actually stands — launch progress
            before you have customers, the numbers once you do — and tells you what to do
            about it. Generate one to start the day.
          </p>
        )
      )}
    </section>
  );
}

function CompaniesSection() {
  const companies = useQuery({ queryKey: ["companies"], queryFn: getCompanies });

  if (companies.isLoading) {
    return <section className="hud-panel p-4 text-[12px] text-text-muted">Loading companies…</section>;
  }
  if (companies.isError || !companies.data) {
    return (
      <section className="hud-panel p-4 text-[12px] text-status-needs-review">
        Could not load companies — is the backend running?
      </section>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {companies.data.map((company) => (
        <CompanyCard key={company.id} company={company} />
      ))}
    </div>
  );
}

function CompanyCard({ company }: { company: Company }) {
  const preRevenue = isPreRevenue(company);
  const metrics = useQuery({
    queryKey: ["company-metrics", company.id],
    queryFn: () => getCompanyMetrics(company.id),
    // A company that hasn't launched has no metrics to fetch -- asking for
    // them is what makes an empty grid look like missing data rather than a
    // business that simply doesn't have customers yet.
    enabled: !preRevenue,
  });

  const latest: BusinessMetricSnapshot | undefined = metrics.data?.[0];
  const previous: BusinessMetricSnapshot | undefined = metrics.data?.[1];

  return (
    <section className="hud-panel p-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-[15px] font-semibold text-text-primary">{company.name}</h2>
          <p className="text-[11px] text-text-muted">
            {company.industry || "—"} · {company.stage}
          </p>
        </div>
        <span className="hud-label text-[9px] text-text-muted">
          {preRevenue
            ? "pre-launch"
            : latest
              ? `updated ${new Date(latest.recorded_at).toLocaleDateString()}`
              : "no data yet"}
        </span>
      </div>

      {preRevenue ? (
        <LaunchPlanPanel company={company} />
      ) : latest ? (
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          <Metric label="MRR" value={money(latest.mrr)} delta={previous && latest.mrr - previous.mrr} isMoney />
          <Metric
            label="Revenue (month)"
            value={money(latest.revenue_this_month)}
            delta={previous && latest.revenue_this_month - previous.revenue_this_month}
            isMoney
          />
          <Metric
            label="Customers"
            value={String(latest.customers)}
            delta={previous && latest.customers - previous.customers}
          />
          <Metric label="Active users" value={String(latest.active_users)} />
          <Metric
            label="Open tickets"
            value={String(latest.support_open_tickets)}
            invertDelta
            delta={previous && latest.support_open_tickets - previous.support_open_tickets}
          />
          <Metric label="Pipeline" value={money(latest.sales_pipeline_value)} isMoney />
          <Metric label="Cash" value={money(latest.cash_balance)} isMoney />
          <Metric label="Burn /mo" value={money(latest.burn_rate_monthly)} isMoney />
          <Metric
            label="New customers"
            value={`+${latest.new_customers_this_month}`}
          />
          <Metric
            label="Churned"
            value={String(latest.churned_customers_this_month)}
            invertDelta
          />
          <Metric label="Mktg spend" value={money(latest.marketing_spend_this_month)} isMoney />
          <Metric
            label="Runway"
            value={
              latest.burn_rate_monthly > 0
                ? `${(latest.cash_balance / latest.burn_rate_monthly).toFixed(1)} mo`
                : "∞"
            }
          />
        </div>
      ) : (
        <p className="mt-3 text-[12px] text-text-muted">
          No metric snapshots yet. Tell JARVIS the numbers (e.g. &quot;record TradeW metrics: MRR
          12k, 340 customers…&quot;) or POST them to /companies/{company.id}/metrics.
        </p>
      )}
    </section>
  );
}

const MILESTONE_STATUS: Record<MilestoneStatus, { label: string; className: string }> = {
  todo: { label: "To do", className: "border-border text-text-muted" },
  in_progress: { label: "In progress", className: "border-status-executing/60 text-status-executing" },
  done: { label: "Done", className: "border-status-completed/60 text-status-completed" },
  blocked: { label: "Blocked", className: "border-status-needs-review/60 text-status-needs-review" },
};

const NEXT_STATUS: Record<MilestoneStatus, MilestoneStatus> = {
  todo: "in_progress",
  in_progress: "done",
  done: "todo",
  blocked: "in_progress",
};

/**
 * What the dashboard shows for a company that hasn't launched. There is no
 * revenue, no customers and no runway to report, so showing a metrics grid
 * would be showing zeros or fiction. Instead JARVIS shows the route to the
 * next stage: what must ship, who owns it, and what is blocked.
 */
function LaunchPlanPanel({ company }: { company: Company }) {
  const queryClient = useQueryClient();
  const milestones = useQuery({
    queryKey: ["milestones", company.id],
    queryFn: () => getMilestones(company.id),
  });
  const [assessment, setAssessment] = useState<string>("");
  const [criticalPath, setCriticalPath] = useState<string>("");

  const plan = useMutation({
    mutationFn: () => generateLaunchPlan(company.id),
    onSuccess: (result) => {
      setAssessment(result.current_stage_assessment);
      setCriticalPath(result.critical_path);
      queryClient.invalidateQueries({ queryKey: ["milestones", company.id] });
    },
  });

  const advance = useMutation({
    mutationFn: ({ id, status }: { id: string; status: MilestoneStatus }) =>
      setMilestoneStatus(company.id, id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["milestones", company.id] }),
  });

  const items: Milestone[] = milestones.data ?? [];
  const done = items.filter((m) => m.status === "done").length;

  return (
    <div className="mt-3 flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[12px] text-text-muted">
          Not launched yet — no customers or revenue to report. This is the route there.
          {items.length > 0 && (
            <span className="text-text-primary">
              {" "}
              {done}/{items.length} done
            </span>
          )}
        </p>
        <button
          type="button"
          onClick={() => plan.mutate()}
          disabled={plan.isPending}
          className="shrink-0 rounded border border-accent-cyan/50 px-3 py-1.5 text-[12px] text-accent-cyan transition-colors hover:bg-accent-cyan/10 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {plan.isPending ? "Planning…" : items.length > 0 ? "Replan" : "Plan the launch"}
        </button>
      </div>

      {plan.isError && (
        <p className="text-[12px] text-status-needs-review">
          {plan.error instanceof Error ? plan.error.message : "Planning failed"}
        </p>
      )}

      {assessment && (
        <div className="rounded border border-border bg-surface-raised/60 p-3">
          <p className="hud-label mb-1 text-[9px] text-text-muted">Where TradeW actually is</p>
          <p className="text-[12px] leading-relaxed text-text-primary/90">{assessment}</p>
          {criticalPath && (
            <p className="mt-2 text-[12px] text-accent-cyan">Critical path: {criticalPath}</p>
          )}
        </div>
      )}

      {items.length === 0 && !plan.isPending ? (
        <p className="text-[12px] text-text-muted">
          No launch plan yet. Ask the Chief of Staff to plan the route to launch — or just say
          it out loud to JARVIS.
        </p>
      ) : (
        <ol className="space-y-2">
          {items.map((milestone, index) => {
            const status = MILESTONE_STATUS[milestone.status];
            return (
              <li
                key={milestone.id}
                className="flex items-start gap-3 rounded border border-border bg-surface-raised/60 p-2.5"
              >
                <span className="hud-label mt-0.5 text-[10px] text-text-muted">{index + 1}</span>
                <div className="min-w-0 flex-1">
                  <p
                    className={`text-[13px] ${
                      milestone.status === "done"
                        ? "text-text-muted line-through"
                        : "text-text-primary"
                    }`}
                  >
                    {milestone.title}
                  </p>
                  {milestone.detail && (
                    <p className="mt-0.5 text-[11px] text-text-muted">{milestone.detail}</p>
                  )}
                  <p className="mt-1 text-[10px] text-accent-cyan">{milestone.owner_agent}</p>
                  {milestone.blocker && (
                    <p className="mt-1 text-[11px] text-status-needs-review">
                      Blocked: {milestone.blocker}
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() =>
                    advance.mutate({ id: milestone.id, status: NEXT_STATUS[milestone.status] })
                  }
                  disabled={advance.isPending}
                  title={`Mark as ${MILESTONE_STATUS[NEXT_STATUS[milestone.status]].label}`}
                  className={`shrink-0 rounded border px-2 py-1 text-[10px] uppercase transition-colors hover:bg-white/5 disabled:opacity-40 ${status.className}`}
                >
                  {status.label}
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  delta,
  isMoney = false,
  invertDelta = false,
}: {
  label: string;
  value: string;
  delta?: number;
  isMoney?: boolean;
  invertDelta?: boolean;
}) {
  const good = delta !== undefined && (invertDelta ? delta < 0 : delta > 0);
  const bad = delta !== undefined && delta !== 0 && !good;
  return (
    <div className="rounded border border-border bg-surface-raised/60 p-2.5">
      <p className="hud-label text-[9px] text-text-muted">{label}</p>
      <p className="mt-1 text-[15px] font-semibold text-text-primary">{value}</p>
      {delta !== undefined && delta !== 0 && (
        <p className={`text-[10px] ${good ? "text-status-completed" : bad ? "text-status-needs-review" : "text-text-muted"}`}>
          {delta > 0 ? "▲" : "▼"} {isMoney ? money(Math.abs(delta)) : Math.abs(delta)}
        </p>
      )}
    </div>
  );
}

function ApprovalsPanel() {
  const queryClient = useQueryClient();
  const approvals = useQuery({ queryKey: ["approvals"], queryFn: () => getApprovals("pending") });
  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "approved" | "rejected" }) =>
      decideApproval(id, decision),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["approvals"] }),
  });

  return (
    <section className="hud-panel p-4">
      <p className="hud-label text-[11px] text-text-primary">Waiting on you</p>
      {approvals.isLoading && <p className="mt-2 text-[12px] text-text-muted">Loading…</p>}
      {approvals.data && approvals.data.length === 0 && (
        <p className="mt-2 text-[12px] text-text-muted">No pending decisions. Clear desk.</p>
      )}
      <ul className="mt-2 space-y-2">
        {approvals.data?.map((approval) => (
          <li key={approval.id} className="rounded border border-border bg-surface-raised/60 p-2.5">
            <p className="text-[13px] text-text-primary">{approval.title}</p>
            {approval.detail && <p className="mt-0.5 text-[11px] text-text-muted">{approval.detail}</p>}
            <div className="mt-2 flex items-center gap-2">
              <span className="hud-label mr-auto text-[9px] text-text-muted">
                {approval.requested_by}
              </span>
              <button
                type="button"
                onClick={() => decide.mutate({ id: approval.id, decision: "approved" })}
                disabled={decide.isPending}
                className="rounded border border-status-completed/50 px-2.5 py-1 text-[11px] text-status-completed hover:bg-status-completed/10 disabled:opacity-40"
              >
                Approve
              </button>
              <button
                type="button"
                onClick={() => decide.mutate({ id: approval.id, decision: "rejected" })}
                disabled={decide.isPending}
                className="rounded border border-status-needs-review/50 px-2.5 py-1 text-[11px] text-status-needs-review hover:bg-status-needs-review/10 disabled:opacity-40"
              >
                Reject
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function NotificationsHint() {
  return (
    <section className="hud-panel p-4">
      <p className="hud-label text-[11px] text-text-primary">Company operations</p>
      <ul className="mt-2 space-y-2 text-[12px] text-text-muted">
        <li>
          <span className="text-text-primary">Ask by voice</span> — &quot;What&apos;s the state of
          TradeW?&quot;, &quot;What should I focus on today?&quot;, &quot;Draft a campaign brief for
          the Marketing Director.&quot;
        </li>
        <li>
          <span className="text-text-primary">Deep work</span> — full multi-agent missions
          (research → plan → build) live in <span className="text-accent-cyan">Missions</span>.
        </li>
        <li>
          <span className="text-text-primary">Memory</span> — everything JARVIS learns lands in
          the <span className="text-accent-cyan">Brain</span> and Knowledge pages.
        </li>
      </ul>
    </section>
  );
}
