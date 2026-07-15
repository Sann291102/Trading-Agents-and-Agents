"use client";

import { useEffect, useRef, useState, useSyncExternalStore, type MutableRefObject } from "react";

import { useOrgStore, type OrgNotification } from "@/store/orgStore";

/** Minimum time (ms) a caption stays fully visible before it is allowed to
 * fade, so short messages don't flash by unreadably fast when narration is
 * muted (and speech duration isn't available to pace against). */
const MIN_DISPLAY_MS = 3200;
/** Rough reading pace used only as a fallback pacing clock when speech
 * synthesis is muted/unavailable -- never used to fabricate any on-screen
 * data, purely a timer for how long a caption line lingers before the next
 * queued one can appear. */
const MS_PER_CHAR = 55;
const MAX_DISPLAY_MS = 9000;
/** How long a caption stays visible after it finishes being narrated /
 * after its paced display window, before fading out. */
const FADE_AFTER_MS = 4000;
/** CSS transition duration for the fade-out itself. */
const FADE_TRANSITION_MS = 700;

function estimateDisplayDuration(message: string): number {
  return Math.min(MAX_DISPLAY_MS, Math.max(MIN_DISPLAY_MS, message.length * MS_PER_CHAR));
}

function hasSpeechSynthesis(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/** Stable no-op subscription: browser speech-synthesis support never
 * changes after load, so useSyncExternalStore only needs to reconcile the
 * server (always unsupported) snapshot with the real client snapshot once
 * during hydration -- no effect/setState cascade required. */
function subscribeToNothing(): () => void {
  return () => {};
}

function getServerSpeechSupportSnapshot(): boolean {
  return false;
}

interface NarrationCaption {
  id: string;
  message: string;
}

interface NarrationQueueContext {
  queueRef: MutableRefObject<OrgNotification[]>;
  speakingRef: MutableRefObject<boolean>;
  mutedRef: MutableRefObject<boolean>;
  speechSupportedRef: MutableRefObject<boolean>;
  fadeTimeoutRef: MutableRefObject<ReturnType<typeof setTimeout> | null>;
  advanceTimeoutRef: MutableRefObject<ReturnType<typeof setTimeout> | null>;
  setCaption: (value: NarrationCaption) => void;
  setCaptionVisible: (value: boolean) => void;
}

/**
 * Drains the narration queue one notification at a time: never overlaps
 * utterances, always advances (via the Web Speech API's utterance end event
 * when speaking, or a paced timer when muted/unsupported) to the next
 * queued notification. Deliberately a plain module-level function (not a
 * hook) so it can recurse via `finishAndAdvance` without re-render churn.
 */
function advanceNarrationQueue(ctx: NarrationQueueContext): void {
  if (ctx.speakingRef.current) return;
  const next = ctx.queueRef.current.shift();
  if (!next) return;

  ctx.speakingRef.current = true;
  ctx.setCaption({ id: next.id, message: next.event.message });
  ctx.setCaptionVisible(true);

  if (ctx.fadeTimeoutRef.current) clearTimeout(ctx.fadeTimeoutRef.current);
  ctx.fadeTimeoutRef.current = setTimeout(() => ctx.setCaptionVisible(false), FADE_AFTER_MS);

  const finishAndAdvance = () => {
    ctx.speakingRef.current = false;
    advanceNarrationQueue(ctx);
  };

  if (!ctx.mutedRef.current && ctx.speechSupportedRef.current) {
    try {
      const utterance = new SpeechSynthesisUtterance(next.event.message);
      utterance.onend = finishAndAdvance;
      utterance.onerror = finishAndAdvance;
      window.speechSynthesis.speak(utterance);
      return;
    } catch {
      // Fall through to the paced timer below.
    }
  }

  ctx.advanceTimeoutRef.current = setTimeout(
    finishAndAdvance,
    estimateDisplayDuration(next.event.message),
  );
}

/**
 * Spoken narration + on-screen captions for organizational milestones.
 *
 * Reads useOrgStore().notifications (already filtered upstream to the
 * significant cross-department events) and, for every notification not yet
 * narrated, speaks its message via the Web Speech API while surfacing a
 * fading caption line. A ref-backed queue guarantees utterances never
 * overlap. Muting stops/skips speech but keeps captions flowing, paced by
 * an estimated reading duration instead.
 */
export function ExecutiveNarration() {
  const notifications = useOrgStore((state) => state.notifications);

  const [muted, setMuted] = useState(false);
  const [caption, setCaption] = useState<NarrationCaption | null>(null);
  const [captionVisible, setCaptionVisible] = useState(false);

  // Browser speech-synthesis support: identical snapshot on every client
  // render (feature detection doesn't change at runtime), but false on the
  // server -- useSyncExternalStore reconciles that safely across hydration
  // without an effect+setState cascade.
  const speechSupported = useSyncExternalStore(
    subscribeToNothing,
    hasSpeechSynthesis,
    getServerSpeechSupportSnapshot,
  );

  const narratedIdsRef = useRef<Set<string>>(new Set());
  const queueRef = useRef<OrgNotification[]>([]);
  const speakingRef = useRef(false);
  const mutedRef = useRef(muted);
  const speechSupportedRef = useRef(speechSupported);

  const fadeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const advanceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    speechSupportedRef.current = speechSupported;
  }, [speechSupported]);

  useEffect(() => {
    mutedRef.current = muted;
    if (muted && speechSupportedRef.current) {
      window.speechSynthesis.cancel();
    }
  }, [muted]);

  useEffect(() => {
    const fresh = notifications.filter((n) => !narratedIdsRef.current.has(n.id));
    if (fresh.length === 0) return;

    for (const n of fresh) {
      narratedIdsRef.current.add(n.id);
      queueRef.current.push(n);
    }

    advanceNarrationQueue({
      queueRef,
      speakingRef,
      mutedRef,
      speechSupportedRef,
      fadeTimeoutRef,
      advanceTimeoutRef,
      setCaption,
      setCaptionVisible,
    });
  }, [notifications]);

  // Stop any in-flight speech and pending timers on unmount.
  useEffect(() => {
    return () => {
      if (fadeTimeoutRef.current) clearTimeout(fadeTimeoutRef.current);
      if (advanceTimeoutRef.current) clearTimeout(advanceTimeoutRef.current);
      if (speechSupportedRef.current) window.speechSynthesis.cancel();
    };
  }, []);

  const toggleLabel = !speechSupported ? "Captions only" : muted ? "Muted" : "Narrating";

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-16 z-50 flex flex-col items-center gap-2 px-4">
      {caption && (
        <div
          className="hud-panel pointer-events-auto max-w-xl px-5 py-3 text-center shadow-lg transition-opacity ease-out"
          style={{
            opacity: captionVisible ? 1 : 0,
            transitionDuration: `${FADE_TRANSITION_MS}ms`,
          }}
        >
          <p className="hud-label text-[10px] font-semibold text-accent-cyan">
            Executive AI
          </p>
          <p className="mt-1 text-sm leading-snug text-text-primary">{caption.message}</p>
        </div>
      )}

      <button
        type="button"
        onClick={() => setMuted((current) => !current)}
        disabled={!speechSupported}
        aria-pressed={muted}
        aria-label={
          !speechSupported
            ? "Executive narration voice is unavailable in this browser"
            : muted
              ? "Unmute executive narration"
              : "Mute executive narration"
        }
        className="hud-panel hud-label pointer-events-auto flex items-center gap-2 px-3 py-1.5 text-[10px] font-medium text-text-secondary transition-colors hover:text-accent-cyan disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:text-text-secondary"
      >
        <SpeakerIcon muted={muted || !speechSupported} />
        <span>{toggleLabel}</span>
      </button>
    </div>
  );
}

function SpeakerIcon({ muted }: { muted: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={14}
      height={14}
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M4 9v6h4l5 5V4L8 9H4z" />
      {muted ? (
        <path d="M17 9l5 6M22 9l-5 6" />
      ) : (
        <path d="M16.5 8.5a5 5 0 0 1 0 7M19.5 5.5a9 9 0 0 1 0 13" />
      )}
    </svg>
  );
}
