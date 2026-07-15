"use client";

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { useEffect, useRef } from "react";

import type { OrgEvent } from "@/types";
import { useOrgStore, type OrgNotification } from "@/store/orgStore";

/** Auto-dismiss window -- "about 6-8 seconds" per spec. */
const AUTO_DISMISS_MS = 7000;

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

interface NotificationVisual {
  /** Tailwind text-color utility (also used via `bg-current` for the accent bar). */
  colorClass: string;
  icon: string;
  label: string;
}

/** Keyed off event.type -- mirrors the accent scheme called out in the spec:
 * green for approvals, red/needs-review for failures/changes, cyan for
 * research/knowledge, purple for review-waiting. Falls back to a neutral
 * tone for event types that are technically part of EventType but never
 * actually reach the notification stack (the store only notifies a subset). */
function visualForType(type: OrgEvent["type"]): NotificationVisual {
  switch (type) {
    case "approval_granted":
      return { colorClass: "text-status-completed", icon: "✓", label: "Approval Granted" };
    case "changes_requested":
      return { colorClass: "text-status-needs_review", icon: "✎", label: "Changes Requested" };
    case "workflow_failed":
      return { colorClass: "text-status-needs_review", icon: "!", label: "Workflow Failed" };
    case "workflow_cancelled":
      return { colorClass: "text-status-waiting", icon: "■", label: "Mission Stopped" };
    case "knowledge_added":
      return { colorClass: "text-accent-cyan", icon: "◆", label: "Knowledge Added" };
    case "research_complete":
      return { colorClass: "text-accent-cyan", icon: "◎", label: "Research Complete" };
    case "review_requested":
      return { colorClass: "text-status-waiting", icon: "◑", label: "Review Requested" };
    case "deployment_started":
      return { colorClass: "text-accent-blue", icon: "▲", label: "Deployment Started" };
    case "deployment_finished":
      return { colorClass: "text-status-completed", icon: "▲", label: "Deployment Finished" };
    default:
      return { colorClass: "text-text-secondary", icon: "●", label: "Update" };
  }
}

function NotificationCard({ notification }: { notification: OrgNotification }) {
  const cardRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dismissedRef = useRef(false);

  const { event } = notification;
  const visual = visualForType(event.type);
  const meta = [event.department, event.agent_role].filter(Boolean).join(" · ");

  useGSAP(
    () => {
      const node = cardRef.current;
      if (!node) return;

      if (prefersReducedMotion()) {
        gsap.set(node, { opacity: 1, x: 0, scale: 1 });
        return;
      }

      gsap.fromTo(
        node,
        { opacity: 0, x: 32, scale: 0.96 },
        { opacity: 1, x: 0, scale: 1, duration: 0.35, ease: "power3.out" }
      );
    },
    { scope: cardRef }
  );

  function requestDismiss() {
    if (dismissedRef.current) return;
    dismissedRef.current = true;

    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }

    const id = notification.id;
    const node = cardRef.current;

    if (!node || prefersReducedMotion()) {
      useOrgStore.getState().dismissNotification(id);
      return;
    }

    gsap.to(node, {
      opacity: 0,
      x: 32,
      scale: 0.96,
      duration: 0.25,
      ease: "power2.in",
      onComplete: () => useOrgStore.getState().dismissNotification(id),
    });
  }

  useEffect(() => {
    timerRef.current = setTimeout(requestDismiss, AUTO_DISMISS_MS);
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
    // Timer is armed once per card (stable notification.id) -- requestDismiss
    // itself guards against double-firing via dismissedRef, and any tween it
    // starts is harmless (a no-op dismiss) even if this card is unmounted
    // externally (e.g. evicted by the store's notification cap) before it fires.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      ref={cardRef}
      role="status"
      className={`glass-panel pointer-events-auto relative w-80 max-w-[calc(100vw-2rem)] overflow-hidden p-3 pl-4 shadow-2xl ${visual.colorClass}`}
    >
      <div className="absolute inset-y-0 left-0 w-1 bg-current" />
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 text-base leading-none" aria-hidden="true">
          {visual.icon}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-medium uppercase tracking-wide">{visual.label}</p>
          <p className="mt-0.5 max-h-32 overflow-y-auto break-words text-sm text-text-primary">
            {event.message}
          </p>
          {meta && <p className="mt-1 text-[11px] text-text-muted">{meta}</p>}
        </div>
        <button
          type="button"
          onClick={requestDismiss}
          aria-label="Dismiss notification"
          className="-mr-1 -mt-1 shrink-0 rounded p-1 text-text-muted transition-colors hover:text-text-primary"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

export function NotificationStack() {
  const notifications = useOrgStore((state) => state.notifications);

  return (
    <div
      role="region"
      aria-label="Notifications"
      aria-live="polite"
      className="pointer-events-none fixed bottom-6 right-6 z-50 flex flex-col-reverse gap-3"
    >
      {notifications.map((notification) => (
        <NotificationCard key={notification.id} notification={notification} />
      ))}
    </div>
  );
}
