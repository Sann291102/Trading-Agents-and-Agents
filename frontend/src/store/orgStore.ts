import { create } from "zustand";

import type { AgentInfo, AgentStatusValue, OrgEvent } from "@/types";

export type ConnectionStatus = "connecting" | "open" | "closed";

export interface OrgNotification {
  id: string;
  event: OrgEvent;
  createdAt: number;
}

/** Event types significant enough to surface as a notification/narration
 * line -- mirrors the backend's distinction between coarse organizational
 * events (these) and fine-grained per-agent agent_started/agent_finished
 * chatter (not notified, only reflected in per-agent status). */
const NOTIFIABLE_TYPES = new Set<OrgEvent["type"]>([
  "research_complete",
  "review_requested",
  "approval_granted",
  "changes_requested",
  "workflow_failed",
  "workflow_cancelled",
  "knowledge_added",
  "deployment_started",
  "deployment_finished",
]);

const MAX_EVENTS = 200;
const MAX_NOTIFICATIONS = 6;

interface OrgState {
  agents: Record<string, AgentInfo>;
  events: OrgEvent[];
  notifications: OrgNotification[];
  connectionStatus: ConnectionStatus;
  /** Department the live workflow/camera should currently focus -- derived
   * from the most recent event carrying a department, so it always
   * reflects where real work is happening right now. */
  activeDepartment: string | null;
  activeProjectId: string | null;
  /** Live-preview state for the most recently completed mission -- set from
   * the `deployment_finished` SSE event's payload (see applyEvent below).
   * Store-level (not component-local) so it survives PromptBar remounts and
   * any other panel can read it later. */
  previewUrl: string | null;
  previewError: string | null;
  /** True strictly between the backend's `deployment_started` and
   * `deployment_finished` events for the preview stage -- distinct from
   * "some agent somewhere is executing" (true for nearly the whole
   * mission), so PreviewPanel only shows a "building" state once the
   * mission has actually reached the preview step. */
  previewBuilding: boolean;

  setAgents: (agents: AgentInfo[]) => void;
  applyEvent: (event: OrgEvent) => void;
  dismissNotification: (id: string) => void;
  setConnectionStatus: (status: ConnectionStatus) => void;
  setActiveDepartment: (department: string | null) => void;
  setPreview: (url: string | null, error: string | null) => void;
}

function statusFromFinishedEvent(event: OrgEvent): AgentStatusValue {
  const hasError = Boolean((event.payload as { error?: unknown } | null)?.error);
  return hasError ? "needs_review" : "completed";
}

export const useOrgStore = create<OrgState>((set) => ({
  agents: {},
  events: [],
  notifications: [],
  connectionStatus: "connecting",
  activeDepartment: null,
  activeProjectId: null,
  previewUrl: null,
  previewError: null,
  previewBuilding: false,

  setAgents: (agents) =>
    set({ agents: Object.fromEntries(agents.map((agent) => [agent.role, agent])) }),

  applyEvent: (event) =>
    set((state) => {
      const events = [...state.events, event].slice(-MAX_EVENTS);

      let agents = state.agents;
      if (
        (event.type === "agent_started" || event.type === "agent_finished") &&
        event.agent_role
      ) {
        const existing = agents[event.agent_role];
        const isStart = event.type === "agent_started";
        agents = {
          ...agents,
          [event.agent_role]: {
            role: event.agent_role,
            department: event.department ?? existing?.department ?? "General",
            status: isStart ? "executing" : statusFromFinishedEvent(event),
            last_confidence: isStart
              ? (existing?.last_confidence ?? null)
              : event.confidence,
            last_duration_seconds: isStart
              ? (existing?.last_duration_seconds ?? null)
              : event.duration_seconds,
            last_project_id: event.project_id,
            last_message: event.message,
          },
        };
      }

      const notifications = NOTIFIABLE_TYPES.has(event.type)
        ? [
            ...state.notifications,
            { id: event.id, event, createdAt: Date.now() },
          ].slice(-MAX_NOTIFICATIONS)
        : state.notifications;

      const previewBuilding =
        event.type === "deployment_started"
          ? true
          : event.type === "deployment_finished"
            ? false
            : state.previewBuilding;

      // The mission now runs on a background thread and POST /projects
      // returns before it finishes (see api/main.py), so preview_url/
      // preview_error can no longer come from that response -- the
      // deployment_finished event's payload (set by graph.py's
      // preview_node) is the only place they're available.
      let previewUrl = state.previewUrl;
      let previewError = state.previewError;
      if (event.type === "deployment_finished") {
        const payload = event.payload as { preview_url?: string; preview_error?: string };
        previewUrl = payload.preview_url ?? null;
        previewError = payload.preview_error ?? null;
      }

      return {
        events,
        agents,
        notifications,
        activeDepartment: event.department ?? state.activeDepartment,
        activeProjectId: event.project_id ?? state.activeProjectId,
        previewBuilding,
        previewUrl,
        previewError,
      };
    }),

  dismissNotification: (id) =>
    set((state) => ({
      notifications: state.notifications.filter((notification) => notification.id !== id),
    })),

  setConnectionStatus: (status) => set({ connectionStatus: status }),
  setActiveDepartment: (department) => set({ activeDepartment: department }),
  setPreview: (url, error) => set({ previewUrl: url, previewError: error }),
}));
