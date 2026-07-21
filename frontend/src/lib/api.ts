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
