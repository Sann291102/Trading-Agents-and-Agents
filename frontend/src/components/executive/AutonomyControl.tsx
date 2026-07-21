"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getAutonomy, runAutonomyOnce, setAutonomy, type AutonomySettings } from "@/lib/api";

function formatInterval(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = seconds / 3600;
  return `${hours % 1 === 0 ? hours : hours.toFixed(1)} hr`;
}

export interface AutonomyControlProps {
  className?: string;
}

/**
 * The switch that lets JARVIS work unsupervised. Autonomy is the one setting
 * a founder must be able to see and revoke at a glance, so the panel states
 * the contract plainly — safe work runs on its own, anything irreversible
 * becomes an approval — rather than hiding it behind a settings page.
 */
export function AutonomyControl({ className = "" }: AutonomyControlProps) {
  const queryClient = useQueryClient();
  const autonomy = useQuery({ queryKey: ["autonomy"], queryFn: getAutonomy });

  const update = useMutation({
    mutationFn: (settings: Partial<AutonomySettings>) => setAutonomy(settings),
    onSuccess: (settings) => queryClient.setQueryData(["autonomy"], settings),
  });

  const runNow = useMutation({
    mutationFn: runAutonomyOnce,
    // A cycle both performs safe work and parks sensitive work for review, so
    // the founder must see both surfaces update the instant it finishes.
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["action-runs"] });
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
    },
  });

  const settings = autonomy.data;
  const enabled = settings?.enabled ?? false;
  const error = autonomy.isError
    ? autonomy.error
    : update.isError
      ? update.error
      : runNow.isError
        ? runNow.error
        : null;

  const ranCount = runNow.data?.results?.length;

  return (
    <section className={`hud-panel p-4 ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="hud-label text-[11px] text-text-primary">Autonomy</p>
          <p className="mt-0.5 text-[11px] text-text-muted">
            {autonomy.isLoading
              ? "Reading current state…"
              : enabled
                ? `Working on its own · every ${formatInterval(settings?.interval_seconds ?? 0)} · up to ${settings?.max_actions_per_cycle ?? 0} actions per cycle`
                : "Standing by — JARVIS acts only when you ask"}
          </p>
        </div>

        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          aria-label="Let JARVIS act on its own"
          onClick={() => update.mutate({ enabled: !enabled })}
          disabled={autonomy.isLoading || update.isPending}
          className={`relative h-6 w-11 shrink-0 rounded-full border transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
            enabled
              ? "border-status-completed/60 bg-status-completed/20"
              : "border-border bg-surface-raised"
          }`}
        >
          <span
            className={`absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full transition-all ${
              enabled ? "left-6 bg-status-completed" : "left-1 bg-text-muted"
            }`}
          />
        </button>
      </div>

      <p className="mt-3 text-[12px] leading-relaxed text-text-primary/90">
        With autonomy on, JARVIS carries out safe work by itself — internal, reversible things
        like updating milestones, recording metrics and writing notes. Anything irreversible,
        outward-facing or that spends money stops and waits for you in{" "}
        <span className="text-accent-cyan">Waiting on you</span>.
      </p>

      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={() => runNow.mutate()}
          disabled={runNow.isPending}
          className="rounded border border-accent-cyan/50 px-3 py-1.5 text-[12px] text-accent-cyan transition-colors hover:bg-accent-cyan/10 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {runNow.isPending ? "Working…" : "Run a cycle now"}
        </button>

        {runNow.isSuccess && !runNow.isPending && (
          <span className="text-[11px] text-text-muted">
            {ranCount === undefined
              ? "Cycle finished — see Activity."
              : ranCount === 0
                ? "Nothing needed doing right now."
                : `Cycle finished — ${ranCount} action${ranCount === 1 ? "" : "s"}. See Activity.`}
          </span>
        )}
      </div>

      {error && (
        <p className="mt-3 text-[12px] text-status-needs-review">
          {error instanceof Error ? error.message : "Autonomy is unavailable"}
        </p>
      )}
    </section>
  );
}
