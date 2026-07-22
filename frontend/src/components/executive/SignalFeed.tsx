"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  getObservers,
  getSignals,
  resolveSignal,
  runObservationOnce,
  type ObserverStatus,
  type Signal,
} from "@/lib/api";

const SEVERITY: Record<
  Signal["severity"],
  { label: string; text: string; border: string; dot: string }
> = {
  urgent: {
    label: "urgent",
    text: "text-status-needs-review",
    border: "border-status-needs-review/50",
    dot: "bg-status-needs-review",
  },
  notable: {
    label: "notable",
    text: "text-status-executing",
    border: "border-status-executing/50",
    dot: "bg-status-executing",
  },
  info: {
    label: "noted",
    text: "text-text-muted",
    border: "border-border",
    dot: "bg-text-muted",
  },
};

function formatRelativeTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const diffSec = Math.round((Date.now() - date.getTime()) / 1000);
  if (diffSec < 60) return "just now";
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHour = Math.round(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h ago`;
  const diffDay = Math.round(diffHour / 24);
  return `${diffDay}d ago`;
}

export interface SignalFeedProps {
  /** How many signals to pull; the feed shows all of them, newest first. */
  limit?: number;
  className?: string;
}

/**
 * What JARVIS noticed — the counterpart to ActivityFeed, which shows what it
 * did. Observers report the complete current truth on every sweep, so a row
 * here is a condition that is *still true*, and its `times_seen` count is the
 * real story: something seen twelve times is being ignored, not repeated.
 * Polled like the activity feed, because background observation cycles land
 * between renders and the founder shouldn't have to reload to learn something
 * changed.
 */
export function SignalFeed({ limit = 40, className = "" }: SignalFeedProps) {
  const queryClient = useQueryClient();

  const signals = useQuery({
    queryKey: ["signals", limit],
    // Open only, and deliberately *not* unprocessed-only: the autonomy loop
    // marks every signal it reasons about as processed, so filtering those out
    // would delete a still-blocked milestone from the founder's view the
    // moment JARVIS thought about it. Open means "still true", which is the
    // only thing this panel promises.
    queryFn: () => getSignals({ limit, openOnly: true }),
    refetchInterval: 15_000,
  });

  // Which eyes are actually open. Without this an empty feed is ambiguous
  // between "nothing is wrong" and "nothing is being watched" -- the second
  // is a setup problem the founder can fix, and silence would hide it.
  const observers = useQuery({
    queryKey: ["observers"],
    queryFn: getObservers,
    staleTime: 5 * 60_000,
  });

  const lookNow = useMutation({
    mutationFn: runObservationOnce,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["signals"] }),
  });

  const acknowledge = useMutation({
    mutationFn: (signalId: string) => resolveSignal(signalId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["signals"] }),
  });

  const items = signals.data ?? [];
  const foundCount = lookNow.data?.length;
  // Until the roster loads, assume JARVIS is watching: the reassuring empty
  // state is right in the overwhelming majority of installs (business_state
  // needs no config), and flashing a setup warning that resolves itself a
  // moment later would be alarming and wrong.
  const anyWatching = observers.data ? observers.data.some((o) => o.available) : true;
  const error = signals.isError
    ? signals.error
    : lookNow.isError
      ? lookNow.error
      : acknowledge.isError
        ? acknowledge.error
        : null;

  return (
    <section className={`hud-panel flex flex-col p-4 ${className}`}>
      <div className="flex items-center justify-between">
        <p className="hud-label text-[11px] text-text-primary">Signals · what JARVIS noticed</p>
        <span className="hud-label text-[9px] text-text-muted">
          {signals.isFetching ? "watching…" : items.length > 0 ? `${items.length} open` : "clear"}
        </span>
      </div>

      <div className="mt-2.5 flex items-center gap-3">
        <button
          type="button"
          onClick={() => lookNow.mutate()}
          disabled={lookNow.isPending}
          className="rounded border border-accent-cyan/50 px-3 py-1.5 text-[12px] text-accent-cyan transition-colors hover:bg-accent-cyan/10 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {lookNow.isPending ? "Looking…" : "Look now"}
        </button>

        {lookNow.isSuccess && !lookNow.isPending && (
          <span className="text-[11px] text-text-muted">
            {foundCount === undefined
              ? "Had a look around."
              : foundCount === 0
                ? "Had a look — nothing new."
                : `Noticed ${foundCount} new thing${foundCount === 1 ? "" : "s"}.`}
          </span>
        )}
      </div>

      {error && (
        <p className="mt-3 text-[12px] text-status-needs-review">
          {error instanceof Error ? error.message : "Could not load what JARVIS noticed"}
        </p>
      )}

      {signals.isLoading && <p className="mt-3 text-[12px] text-text-muted">Loading…</p>}

      {!signals.isLoading && !signals.isError && items.length === 0 && (
        <p className="mt-3 text-[12px] leading-relaxed text-text-muted">
          {anyWatching
            ? "Nothing to report. JARVIS is keeping an eye on the business and will raise anything worth your attention here — no need to come looking."
            : "Nothing to report — but nothing is being watched either. Set up an observer below and JARVIS will start raising things here on its own."}
        </p>
      )}

      {items.length > 0 && (
        <ol className="mt-3 space-y-1.5">
          {items.map((signal) => (
            <SignalEntry
              key={signal.id}
              signal={signal}
              onAcknowledge={() => acknowledge.mutate(signal.id)}
              pending={acknowledge.isPending && acknowledge.variables === signal.id}
            />
          ))}
        </ol>
      )}

      <WatchingLine observers={observers.data} />
    </section>
  );
}

/**
 * What JARVIS can and cannot see, stated plainly. An observer that is not
 * configured is named rather than hidden: the founder is the only person who
 * can supply the key, and they can only do that if they know it is missing.
 */
function WatchingLine({ observers }: { observers: ObserverStatus[] | undefined }) {
  if (!observers || observers.length === 0) return null;
  const open = observers.filter((observer) => observer.available);
  const closed = observers.filter((observer) => !observer.available);

  return (
    <p className="mt-3 border-t border-border pt-2 text-[10px] leading-relaxed text-text-muted">
      {open.length > 0
        ? `Watching ${open.map((observer) => observer.display_name).join(", ")}.`
        : "Nothing is being watched yet."}
      {closed.length > 0 && (
        <>
          {" "}
          <span
            className="text-text-muted/80"
            title={closed
              .map((observer) => `${observer.display_name}: ${observer.setup_hint}`)
              .join("\n")}
          >
            Not set up: {closed.map((observer) => observer.display_name).join(", ")}.
          </span>
        </>
      )}
    </p>
  );
}

function SignalEntry({
  signal,
  onAcknowledge,
  pending,
}: {
  signal: Signal;
  onAcknowledge: () => void;
  pending: boolean;
}) {
  const [open, setOpen] = useState(false);
  const severity = SEVERITY[signal.severity] ?? SEVERITY.info;
  const repeats = signal.times_seen > 1;
  // A condition reported this many sweeps running is no longer information,
  // it's an unanswered question -- so it stops being grey.
  const nagging = signal.times_seen >= 5;
  // Acknowledged, not gone: the condition is still true (that is what keeps it
  // in an open-only feed), it has just stopped driving JARVIS's next cycle.
  const acknowledged = signal.processed_at !== null;

  return (
    <li
      className={`rounded border bg-surface-raised/60 ${severity.border} ${
        acknowledged ? "opacity-60" : ""
      }`}
    >
      <div className="flex items-start">
        <button
          type="button"
          onClick={() => setOpen((previous) => !previous)}
          aria-expanded={open}
          className="flex min-w-0 flex-1 items-start gap-2.5 p-2.5 text-left transition-colors hover:bg-white/5"
        >
          <span
            className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${severity.dot}`}
            aria-hidden="true"
          />
          <span className="min-w-0 flex-1">
            <span className="block text-[13px] leading-snug text-text-primary">{signal.title}</span>
            <span className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-[10px] text-text-muted">
              <span className={severity.text}>{severity.label}</span>
              <span>·</span>
              <span className="font-mono">{signal.source}</span>
              {repeats && (
                <span
                  className={`hud-label rounded-sm border px-1 py-px text-[9px] ${
                    nagging
                      ? "border-status-needs-review/50 text-status-needs-review"
                      : "border-border text-text-muted"
                  }`}
                >
                  seen {signal.times_seen}x
                </span>
              )}
              {acknowledged && (
                <span className="hud-label rounded-sm border border-border px-1 py-px text-[9px] text-text-muted">
                  acknowledged
                </span>
              )}
            </span>
          </span>
          <span className="hud-label shrink-0 pt-0.5 text-[9px] text-text-muted">
            {formatRelativeTime(signal.last_seen_at)}
          </span>
        </button>

        <button
          type="button"
          onClick={onAcknowledge}
          disabled={pending || acknowledged}
          aria-label={
            acknowledged
              ? `Already acknowledged: ${signal.title}`
              : `I've seen this: ${signal.title}`
          }
          title={
            acknowledged
              ? "Acknowledged — out of JARVIS's inbox. It stays listed while the condition is still true."
              : "I've seen this — takes it out of JARVIS's inbox. It stays listed until the condition ends."
          }
          className="shrink-0 self-stretch px-2.5 text-[13px] leading-none text-text-muted transition-colors hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
        >
          {pending ? "…" : acknowledged ? "✓" : "×"}
        </button>
      </div>

      {open && (
        <div className="border-t border-border px-2.5 py-2">
          {signal.detail && (
            <p className="whitespace-pre-wrap text-[11px] leading-relaxed text-text-primary/90">
              {signal.detail}
            </p>
          )}
          <p className="mt-2 font-mono text-[10px] leading-relaxed text-text-muted">
            {signal.source} · {signal.kind}
            {repeats && <> · seen {signal.times_seen}x</>}
            {" · first noticed "}
            {formatRelativeTime(signal.observed_at)}
          </p>
        </div>
      )}
    </li>
  );
}
