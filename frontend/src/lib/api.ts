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
  const response = await fetch(`${API_BASE_URL}${path}`, init);
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
