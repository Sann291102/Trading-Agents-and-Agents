/** Mirrors GET /agents (aio.agents.registry). One entry per implemented
 * Agent subclass -- new departments appear here with zero frontend
 * changes the moment the backend adds a new Agent subclass. */
export type AgentStatusValue = "idle" | "executing" | "completed" | "needs_review";

export interface AgentInfo {
  role: string;
  department: string;
  status: AgentStatusValue;
  last_confidence: number | null;
  last_duration_seconds: number | null;
  last_project_id: string | null;
  last_message: string;
}
