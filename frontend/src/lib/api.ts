import { useOrgStore } from "@/store/orgStore";
import type {
  AgentInfo,
  ExecutionLogEntry,
  MemoryEntry,
  ProjectResponse,
  ProjectSummary,
} from "@/types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  // Every operator-facing backend endpoint requires a bearer token (see
  // aio/api/main.py's get_current_user) except /health and /auth/*, which
  // ignore this header if present -- so attaching it unconditionally here,
  // in one place, is simpler than threading auth through every call site.
  const token = useOrgStore.getState().token;
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(`${init?.method ?? "GET"} ${path} failed (${response.status}): ${body}`);
  }
  return response.json() as Promise<T>;
}

export interface HealthResponse {
  status: string;
  llm_provider: string;
  model: string;
}

export function getHealth() {
  return fetchJSON<HealthResponse>("/health");
}

export function getAgents() {
  return fetchJSON<AgentInfo[]>("/agents");
}

export function getProjects(limit = 50) {
  return fetchJSON<ProjectSummary[]>(`/projects?limit=${limit}`);
}

export function getProject(id: string) {
  return fetchJSON<ProjectResponse>(`/projects/${encodeURIComponent(id)}`);
}

/**
 * Where a mission's generated code actually lives on disk
 * (workspace/previews/<project_id> on the backend) -- relative file paths,
 * walked fresh from disk on every call since there's no DB manifest (see
 * aio/api/main.py's list_project_files). Throws a 404 via fetchJSON when
 * the mission never reached the swarm/preview stage.
 */
export function listPreviewFiles(id: string) {
  return fetchJSON<string[]>(`/projects/${encodeURIComponent(id)}/files`);
}

export interface ProjectSearchHit {
  id: string;
  score: number;
  goal?: string;
  summary?: string;
}

export function searchProjects(query: string, topK = 5) {
  return fetchJSON<ProjectSearchHit[]>(
    `/projects/search?q=${encodeURIComponent(query)}&top_k=${topK}`
  );
}

export function getExecutionLogs(limit = 100) {
  return fetchJSON<ExecutionLogEntry[]>(`/execution-logs?limit=${limit}`);
}

/**
 * Durable organizational memory (research findings, risks, ...) recorded per
 * run -- see src/aio/memory/recording.py. The backend endpoint is list-only
 * (MemoryService is deliberately CRUD-only, no server-side filtering yet),
 * so callers that want one project's entries filter on `project_id` client
 * side.
 */
export function getMemoryEntries(limit = 50) {
  return fetchJSON<MemoryEntry[]>(`/memory-entries?limit=${limit}`);
}

export interface StartProjectResponse {
  project_id: string;
}

/**
 * Kicks off the real orchestration pipeline on the backend and returns the
 * new project_id immediately (HTTP 202) -- the backend runs the mission on
 * a background thread rather than blocking the request, since a real run is
 * a dozen-plus sequential/parallel LLM calls. Callers track progress via the
 * live SSE event stream (already reflects each agent starting/finishing)
 * and via `getProject(project_id)` once the mission finishes and persists.
 */
export function startProject(goal: string) {
  return fetchJSON<StartProjectResponse>("/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goal }),
  });
}

export interface CancelProjectResponse {
  status: string;
}

/**
 * Requests cooperative cancellation of an in-flight mission -- the backend
 * checks this at each agent boundary (see aio/orchestration/cancellation.py)
 * and stops making further LLM calls, it does not kill mid-flight work
 * instantly. Throws (via fetchJSON) on a 404 if the mission already
 * finished before the cancel request arrived.
 */
export function cancelProject(projectId: string) {
  return fetchJSON<CancelProjectResponse>(`/projects/${encodeURIComponent(projectId)}/cancel`, {
    method: "POST",
  });
}

export interface ResumeProjectResponse {
  status: string;
  project_id: string;
}

/**
 * Resume a failed mission on the same project after fixing the LLM
 * provider/API key in .env -- the backend re-reads config and continues the
 * mission's checkpointed graph from its last completed node (404 if the
 * mission isn't in a resumable state, e.g. the server restarted).
 */
export function resumeProject(projectId: string) {
  return fetchJSON<ResumeProjectResponse>(`/projects/${encodeURIComponent(projectId)}/resume`, {
    method: "POST",
  });
}

export interface ChatResponse {
  reply: string;
}

/**
 * The Brain page's casual-question path -- one direct LLM call grounded in
 * real semantic-memory search results (see aio/api/main.py's `chat`
 * endpoint), not the full multi-agent mission graph. For quick questions
 * only; the backend's own system prompt redirects anything that actually
 * needs building back to `startProject`.
 */
export function askBrain(message: string) {
  return fetchJSON<ChatResponse>("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
}

// ---------------------------------------------------------------------------
// Executive Business OS -- companies, metrics, approvals, briefing, assistant
// ---------------------------------------------------------------------------

export interface Company {
  id: string;
  name: string;
  description: string;
  industry: string;
  stage: string;
  website: string;
  created_at: string;
}

export interface BusinessMetricSnapshot {
  id: string;
  company_id: string;
  mrr: number;
  revenue_this_month: number;
  customers: number;
  new_customers_this_month: number;
  churned_customers_this_month: number;
  active_users: number;
  support_open_tickets: number;
  marketing_spend_this_month: number;
  sales_pipeline_value: number;
  cash_balance: number;
  burn_rate_monthly: number;
  notes: string;
  recorded_at: string;
}

export const PRE_REVENUE_STAGES = ["idea", "building"];

export function isPreRevenue(company: Company): boolean {
  return PRE_REVENUE_STAGES.includes(company.stage);
}

export type MilestoneStatus = "todo" | "in_progress" | "done" | "blocked";

export interface Milestone {
  id: string;
  company_id: string;
  title: string;
  detail: string;
  stage_target: string;
  owner_agent: string;
  status: MilestoneStatus;
  blocker: string;
  created_at: string;
  completed_at: string | null;
}

export interface LaunchPlanResult {
  target_stage: string;
  current_stage_assessment: string;
  critical_path: string;
  confidence: number;
  milestones: Milestone[];
}

export function getMilestones(companyId: string) {
  return fetchJSON<Milestone[]>(`/companies/${encodeURIComponent(companyId)}/milestones`);
}

/** The Chief of Staff plans the route to the company's next stage. */
export function generateLaunchPlan(companyId: string) {
  return fetchJSON<LaunchPlanResult>(`/companies/${encodeURIComponent(companyId)}/launch-plan`, {
    method: "POST",
  });
}

export function setMilestoneStatus(
  companyId: string,
  milestoneId: string,
  status: MilestoneStatus,
  blocker = ""
) {
  return fetchJSON<Milestone>(
    `/companies/${encodeURIComponent(companyId)}/milestones/${encodeURIComponent(
      milestoneId
    )}/status`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, blocker }),
    }
  );
}

export interface Approval {
  id: string;
  company_id: string | null;
  title: string;
  detail: string;
  requested_by: string;
  status: "pending" | "approved" | "rejected";
  created_at: string;
  decided_at: string | null;
}

export interface PriorityItem {
  title: string;
  why_now: string;
  owner_agent: string;
  impact: "high" | "medium" | "low";
}

export interface BusinessRisk {
  title: string;
  severity: "critical" | "high" | "medium" | "low";
  mitigation: string;
}

export interface ExecutiveBriefing {
  confidence: number;
  reasoning_summary: string;
  headline: string;
  business_health: "strong" | "stable" | "warning" | "critical";
  summary: string;
  priorities: PriorityItem[];
  risks: BusinessRisk[];
  opportunities: string[];
  generated_at: string;
}

export interface AssistantReply {
  reply: string;
  suggested_actions: string[];
  /** Action name JARVIS ran for this turn, or "" if it only answered. */
  action?: string;
  /** What that action's execution actually produced, when one ran. */
  result?: { outcome: string; summary: string; detail: string; data: Record<string, unknown> } | null;
}

export interface ConversationTurn {
  who: "founder" | "jarvis";
  text: string;
}

export function getCompanies() {
  return fetchJSON<Company[]>("/companies");
}

export function getCompanyMetrics(companyId: string, limit = 12) {
  return fetchJSON<BusinessMetricSnapshot[]>(
    `/companies/${encodeURIComponent(companyId)}/metrics?limit=${limit}`
  );
}

export function recordCompanyMetrics(
  companyId: string,
  metrics: Partial<Omit<BusinessMetricSnapshot, "id" | "company_id" | "recorded_at">>
) {
  return fetchJSON<BusinessMetricSnapshot>(
    `/companies/${encodeURIComponent(companyId)}/metrics`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(metrics),
    }
  );
}

export function getApprovals(status: "pending" | "approved" | "rejected" | "" = "pending") {
  return fetchJSON<Approval[]>(`/approvals?status=${status}`);
}

export function createApproval(title: string, detail = "", companyId: string | null = null) {
  return fetchJSON<Approval>("/approvals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, detail, company_id: companyId }),
  });
}

export function decideApproval(approvalId: string, decision: "approved" | "rejected") {
  return fetchJSON<Approval>(`/approvals/${encodeURIComponent(approvalId)}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  });
}

/**
 * The Chief of Staff composes today's executive briefing from real company
 * metric snapshots + pending approvals. Fresh LLM synthesis per call.
 */
export function generateBriefing() {
  return fetchJSON<ExecutiveBriefing>("/briefing", { method: "POST" });
}

/**
 * One conversational turn with the Executive Assistant -- the voice-first
 * path. Grounded server-side in the live business snapshot + memory; the
 * conversation so far travels with each call so replies stay contextual.
 */
export function askAssistant(message: string, history: ConversationTurn[] = []) {
  return fetchJSON<AssistantReply>("/assistant", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
}

/** JARVIS's spoken greeting when the founder opens the app. */
export function greetAssistant() {
  return fetchJSON<AssistantReply>("/assistant/greet", { method: "POST" });
}

/** The persisted founder <-> JARVIS conversation tail, oldest first. */
export function getAssistantHistory(limit = 30) {
  return fetchJSON<ConversationTurn[]>(`/assistant/history?limit=${limit}`);
}

// ---------------------------------------------------------------------------
// Autonomy -- the action layer JARVIS actually performs work through
// ---------------------------------------------------------------------------

export type ActionOutcome = "executed" | "escalated" | "failed" | "rejected";

/** One thing JARVIS did, as recorded by the executor. `summary` is past tense. */
export interface ActionRun {
  id: string;
  action: string;
  actor: string;
  params_json: string;
  outcome: ActionOutcome;
  summary: string;
  detail: string;
  created_at: string;
}

export interface ActionSpec {
  name: string;
  description: string;
  /**
   * `safe` runs autonomously (reversible + internal); `sensitive` is parked
   * as an approval first because it is irreversible, outward-facing, or
   * spends money.
   */
  risk: "safe" | "sensitive";
  owner_agent: string;
  connector: string | null;
  params_schema: Record<string, unknown>;
  available: boolean;
}

export interface ConnectorStatus {
  name: string;
  display_name: string;
  description: string;
  capabilities: string[];
  available: boolean;
  setup_hint: string;
}

export interface AutonomySettings {
  enabled: boolean;
  interval_seconds: number;
  max_actions_per_cycle: number;
}

export interface ActionResult {
  outcome: ActionOutcome;
  summary: string;
  detail: string;
  data: Record<string, unknown>;
}

/** Newest first — the same ordering the backend's list_action_runs returns. */
export function getActionRuns(limit = 50) {
  return fetchJSON<ActionRun[]>(`/action-runs?limit=${limit}`);
}

/** Every registered action, including ones whose connector isn't configured. */
export function getActions() {
  return fetchJSON<ActionSpec[]>("/actions");
}

export function getConnectors() {
  return fetchJSON<ConnectorStatus[]>("/connectors");
}

export function getAutonomy() {
  return fetchJSON<AutonomySettings>("/autonomy");
}

/** Partial update — the backend merges onto the settings already in effect. */
export function setAutonomy(settings: Partial<AutonomySettings>) {
  return fetchJSON<AutonomySettings>("/autonomy", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

/**
 * Fires one autonomy cycle immediately instead of waiting for the interval.
 * The response is a convenience echo of what the cycle did; the durable
 * record is the action-run feed, so callers refetch that rather than trust
 * this payload's exact shape.
 */
export interface AutonomyCycleRun {
  results?: ActionResult[];
  [key: string]: unknown;
}

export function runAutonomyOnce() {
  return fetchJSON<AutonomyCycleRun>("/autonomy/run-once", { method: "POST" });
}

/**
 * Runs a single action by name. A `sensitive` action returns outcome
 * `escalated` rather than executing — it becomes a pending approval instead.
 */
export function executeAction(name: string, params: Record<string, unknown>) {
  return fetchJSON<ActionResult>(`/actions/${encodeURIComponent(name)}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ params }),
  });
}

// ---------------------------------------------------------------------------
// Observation -- what JARVIS noticed without being asked
// ---------------------------------------------------------------------------

export type SignalSeverity = "info" | "notable" | "urgent";

/**
 * One thing an observer saw. `dedupe_key` identifies the underlying
 * *condition*, not the moment it was spotted, which is why the same milestone
 * still being blocked tomorrow arrives as `times_seen: 2` on the original
 * signal rather than as a second row. A signal is open until an observer stops
 * reporting it (auto-resolved) or the founder dismisses it.
 */
export interface Signal {
  id: string;
  /** Observer name that raised it, e.g. "milestones". */
  source: string;
  /** Machine name for the condition, e.g. "milestone_blocked". */
  kind: string;
  title: string;
  detail: string;
  severity: SignalSeverity;
  company_id: string | null;
  dedupe_key: string;
  times_seen: number;
  observed_at: string;
  last_seen_at: string;
  processed_at: string | null;
  resolved_at: string | null;
}

export interface ObserverStatus {
  name: string;
  display_name: string;
  description: string;
  available: boolean;
  setup_hint: string;
  /** Human-readable list of the conditions this observer watches for. */
  watches: string[];
}

/** Newest first. Defaults mirror the backend's (all signals, most recent 50). */
export function getSignals(opts: { limit?: number; openOnly?: boolean; unprocessedOnly?: boolean } = {}) {
  const params = new URLSearchParams({
    limit: String(opts.limit ?? 50),
    open_only: String(opts.openOnly ?? false),
    unprocessed_only: String(opts.unprocessedOnly ?? false),
  });
  return fetchJSON<Signal[]>(`/signals?${params.toString()}`);
}

/** Every observer, including ones whose connector/config isn't set up yet. */
export function getObservers() {
  return fetchJSON<ObserverStatus[]>("/observers");
}

/**
 * Sweeps every available observer immediately instead of waiting for the
 * background cycle. Returns only the *new* signals: repeats of conditions
 * already on file are collapsed into their existing signal server-side, so an
 * empty array genuinely means "nothing new", not "nothing happening".
 */
export function runObservationOnce() {
  return fetchJSON<Signal[]>("/observe/run-once", { method: "POST" });
}

export interface SignalResolveResponse {
  status: "resolved" | "processed";
  signal_id: string;
  /** True only if the signal is actually closed. Usually false — see below. */
  resolved: boolean;
  /** True once it is out of JARVIS's inbox, which is what always happens. */
  processed: boolean;
  /** Populated when `resolved` is false, explaining why it stays open. */
  detail: string;
}

/**
 * The founder saying "I've seen this" — which is *acknowledgement*, not
 * closure, and callers must not present it as closure. The backend marks the
 * signal processed (it leaves JARVIS's inbox and stops driving the autonomy
 * loop) but leaves it open, because a condition is only over when the observer
 * that reported it stops reporting it. So a still-blocked milestone stays in
 * the feed after this call, correctly, with `processed_at` set — check
 * `resolved` before telling the founder anything went away.
 */
export function resolveSignal(signalId: string) {
  return fetchJSON<SignalResolveResponse>(`/signals/${encodeURIComponent(signalId)}/resolve`, {
    method: "POST",
  });
}

export interface AuthResponse {
  token: string;
}

export function signup(username: string, password: string) {
  return fetchJSON<AuthResponse>("/auth/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export function login(username: string, password: string) {
  return fetchJSON<AuthResponse>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}
