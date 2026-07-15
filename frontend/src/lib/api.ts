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

/**
 * Fires the real orchestration pipeline. This request can take a while (a
 * dozen-plus sequential/parallel LLM calls) -- callers should not block UI
 * feedback on it resolving, since the live event stream already reflects
 * progress the moment each agent starts/finishes, independent of when this
 * HTTP response returns.
 */
export function createProject(goal: string) {
  return fetchJSON<ProjectResponse>("/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goal }),
  });
}
