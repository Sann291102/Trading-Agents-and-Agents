"use client";

import { useEffect } from "react";

import { API_BASE_URL } from "@/lib/api";
import { useOrgStore } from "@/store/orgStore";
import type { EventType, OrgEvent } from "@/types";

const EVENT_TYPES: EventType[] = [
  "agent_started",
  "agent_finished",
  "task_delegated",
  "research_complete",
  "review_requested",
  "approval_granted",
  "changes_requested",
  "memory_updated",
  "knowledge_added",
  "deployment_started",
  "deployment_finished",
  "workflow_failed",
];

/**
 * Opens the live SSE connection once and feeds every event straight into
 * the Zustand store. Reads/writes go through `useOrgStore.getState()`
 * rather than the reactive hook -- the store's actions are stable
 * references, so there is no stale-closure risk and no need to reopen the
 * EventSource when unrelated state changes (see Phase 3 research notes on
 * Zustand + SSE integration).
 *
 * Call this once, near the app root (see components/OrgProvider.tsx) --
 * not per-component, or every mounted consumer would open its own
 * duplicate connection to the backend.
 */
export function useOrgEventStream() {
  useEffect(() => {
    const source = new EventSource(`${API_BASE_URL}/events/stream`);
    useOrgStore.getState().setConnectionStatus("connecting");

    source.onopen = () => useOrgStore.getState().setConnectionStatus("open");
    source.onerror = () => useOrgStore.getState().setConnectionStatus("closed");

    const handler = (raw: MessageEvent<string>) => {
      const event = JSON.parse(raw.data) as OrgEvent;
      useOrgStore.getState().applyEvent(event);
    };
    for (const type of EVENT_TYPES) {
      source.addEventListener(type, handler as EventListener);
    }

    return () => {
      for (const type of EVENT_TYPES) {
        source.removeEventListener(type, handler as EventListener);
      }
      source.close();
    };
  }, []);
}
