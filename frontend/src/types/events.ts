/**
 * Mirrors aio.events.bus.OrgEvent / aio.events.types.EventType exactly.
 * This is the live-event contract: every value the UI animates traces back
 * to one of these, published by real backend code (Agent.run_logged,
 * orchestration graph nodes, memory writes) -- never synthesized here.
 */
export type EventType =
  | "agent_started"
  | "agent_finished"
  | "task_delegated"
  | "research_complete"
  | "review_requested"
  | "approval_granted"
  | "changes_requested"
  | "memory_updated"
  | "knowledge_added"
  | "deployment_started"
  | "deployment_finished"
  | "workflow_failed";

export interface OrgEvent {
  id: string;
  type: EventType;
  timestamp: string;
  department: string | null;
  agent_role: string | null;
  project_id: string | null;
  confidence: number | null;
  duration_seconds: number | null;
  message: string;
  payload: Record<string, unknown>;
}
