"use client";

import { useState } from "react";

import { askBrain } from "@/lib/api";

import { HudFrame } from "../mission-control/HudFrame";

interface ChatTurn {
  id: string;
  question: string;
  answer: string | null;
  error: string | null;
}

/**
 * Casual-question chat box for the Brain page -- POST /chat, one direct LLM
 * call grounded in real semantic-memory search, not the full mission
 * pipeline. Deliberately in its own file with no Three.js imports (unlike
 * BrainScene) so it can be a normal, non-dynamic import: it doesn't touch
 * `window` at module load time and has nothing that needs ssr:false.
 */
export function BrainChat() {
  const [value, setValue] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const question = value.trim();
    if (!question || pending) return;

    const id = `${turns.length}-${question.slice(0, 12)}`;
    setTurns((current) => [...current, { id, question, answer: null, error: null }]);
    setValue("");
    setPending(true);
    try {
      const result = await askBrain(question);
      setTurns((current) =>
        current.map((turn) => (turn.id === id ? { ...turn, answer: result.reply } : turn))
      );
    } catch (error) {
      setTurns((current) =>
        current.map((turn) =>
          turn.id === id
            ? { ...turn, error: error instanceof Error ? error.message : "Failed to answer" }
            : turn
        )
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <HudFrame className="hud-panel pointer-events-auto absolute bottom-4 left-1/2 z-10 flex w-[36rem] max-w-[calc(100vw-2rem)] -translate-x-1/2 flex-col overflow-hidden">
      {turns.length > 0 && (
        <div className="max-h-48 space-y-2 overflow-y-auto border-b border-border p-3">
          {turns.map((turn) => (
            <div key={turn.id} className="text-xs">
              <p className="text-text-primary">
                <span className="hud-label text-accent-cyan">You </span>
                {turn.question}
              </p>
              {turn.answer && (
                <p className="mt-0.5 text-text-secondary">
                  <span className="hud-label text-accent-purple">Brain </span>
                  {turn.answer}
                </p>
              )}
              {turn.error && <p className="mt-0.5 text-status-needs_review">{turn.error}</p>}
              {!turn.answer && !turn.error && (
                <p className="mt-0.5 italic text-text-muted">thinking…</p>
              )}
            </div>
          ))}
        </div>
      )}
      <form onSubmit={handleSubmit} className="flex items-center gap-2 p-2">
        <span className="hud-label shrink-0 pl-1 text-sm text-accent-purple" aria-hidden="true">
          ?
        </span>
        <input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="Ask about past projects, findings, risks…"
          aria-label="Ask the brain"
          className="min-w-0 flex-1 bg-transparent font-mono text-sm text-text-primary placeholder:text-text-muted outline-none"
        />
        <button
          type="submit"
          disabled={!value.trim() || pending}
          className="hud-label shrink-0 rounded border border-accent-purple/40 bg-accent-purple/10 px-3 py-2 text-[11px] font-medium text-accent-purple transition-colors hover:bg-accent-purple/20 disabled:opacity-50"
        >
          {pending ? "Asking…" : "Ask"}
        </button>
      </form>
    </HudFrame>
  );
}
