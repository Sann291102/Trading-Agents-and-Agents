"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  askAssistant,
  getAssistantHistory,
  greetAssistant,
  type ConversationTurn,
} from "@/lib/api";

/* Minimal typings for the Web Speech API (not yet in lib.dom for all TS
 * versions). Chrome/Edge expose webkitSpeechRecognition; Safari 17+ too. */
interface SpeechRecognitionResultLike {
  0: { transcript: string };
  isFinal: boolean;
}
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: ArrayLike<SpeechRecognitionResultLike>;
}
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
}

function getRecognitionCtor(): (new () => SpeechRecognitionLike) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

interface Turn {
  who: "you" | "jarvis";
  text: string;
}

function toHistory(turns: Turn[]): ConversationTurn[] {
  return turns.map((turn) => ({
    who: turn.who === "you" ? "founder" : "jarvis",
    text: turn.text,
  }));
}

function fromHistory(history: ConversationTurn[]): Turn[] {
  return history.map((turn) => ({
    who: turn.who === "founder" ? ("you" as const) : ("jarvis" as const),
    text: turn.text,
  }));
}

/**
 * Voice-first interaction with JARVIS. Hold a conversation by voice: the
 * mic streams speech-to-text (Web Speech API), a final utterance is sent to
 * the Executive Assistant on the backend (grounded in live business data),
 * and the reply is spoken aloud (speechSynthesis) as well as shown. Typing
 * stays available as the secondary path -- same endpoint, same context.
 */
export function VoiceAssistantBar() {
  const [supported, setSupported] = useState(true);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [interim, setInterim] = useState("");
  const [draft, setDraft] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const listeningRef = useRef(false);
  const speakingRef = useRef(false);
  const turnsRef = useRef<Turn[]>([]);
  const greetedRef = useRef(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setSupported(getRecognitionCtor() !== null);
    return () => {
      recognitionRef.current?.abort();
      if (typeof window !== "undefined") window.speechSynthesis?.cancel();
    };
  }, []);

  useEffect(() => {
    turnsRef.current = turns;
  }, [turns]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [turns, interim]);

  const speak = useCallback((text: string) => {
    if (typeof window === "undefined" || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.05;
    utterance.onstart = () => {
      speakingRef.current = true;
      setSpeaking(true);
    };
    const done = () => {
      speakingRef.current = false;
      setSpeaking(false);
    };
    utterance.onend = done;
    utterance.onerror = done;
    window.speechSynthesis.speak(utterance);
  }, []);

  // Restore the persisted conversation from the backend (JARVIS remembers
  // across sessions and devices); greet only when there is no history yet.
  // The greeting itself is persisted server-side, so reloads restore it
  // instead of re-greeting.
  useEffect(() => {
    if (greetedRef.current) return;
    greetedRef.current = true;
    let cancelled = false;
    getAssistantHistory()
      .then((history) => {
        if (cancelled) return;
        if (history.length > 0) {
          setTurns(fromHistory(history));
          return;
        }
        return greetAssistant().then((greeting) => {
          if (cancelled) return;
          setTurns([{ who: "jarvis", text: greeting.reply }]);
          speak(greeting.reply);
        });
      })
      .catch(() => {
        /* backend not up yet -- the bar still works once it is */
      });
    return () => {
      cancelled = true;
    };
  }, [speak]);

  const submit = useCallback(
    async (message: string) => {
      const trimmed = message.trim();
      if (!trimmed) return;
      const history = toHistory(turnsRef.current.slice(-12));
      setTurns((prev) => [...prev, { who: "you", text: trimmed }]);
      setBusy(true);
      try {
        const response = await askAssistant(trimmed, history);
        const reply =
          response.suggested_actions.length > 0
            ? `${response.reply}\n\nSuggested: ${response.suggested_actions.join("; ")}`
            : response.reply;
        setTurns((prev) => [...prev, { who: "jarvis", text: reply }]);
        speak(response.reply);
      } catch (error) {
        const message_ = error instanceof Error ? error.message : "Assistant unavailable";
        setTurns((prev) => [...prev, { who: "jarvis", text: `⚠ ${message_}` }]);
      } finally {
        setBusy(false);
      }
    },
    [speak]
  );

  const stopListening = useCallback(() => {
    listeningRef.current = false;
    setListening(false);
    setInterim("");
    recognitionRef.current?.stop();
  }, []);

  const startListening = useCallback(() => {
    const Ctor = getRecognitionCtor();
    if (!Ctor) return;
    window.speechSynthesis?.cancel();

    const recognition = new Ctor();
    recognition.lang = navigator.language || "en-US";
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onresult = (event) => {
      // While JARVIS is speaking, the mic hears the TTS voice -- drop those
      // results so JARVIS never talks to itself.
      if (speakingRef.current) {
        setInterim("");
        return;
      }
      let interimText = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result.isFinal) {
          void submit(result[0].transcript);
        } else {
          interimText += result[0].transcript;
        }
      }
      setInterim(interimText);
    };
    recognition.onend = () => {
      // Keep the conversation continuous: the browser ends recognition on
      // silence; restart while the operator still has the mic on.
      if (listeningRef.current) {
        try {
          recognition.start();
        } catch {
          /* already started */
        }
      }
    };
    recognition.onerror = (event) => {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        listeningRef.current = false;
        setListening(false);
        setSupported(false);
      }
    };

    recognitionRef.current = recognition;
    listeningRef.current = true;
    setListening(true);
    recognition.start();
  }, [submit]);

  function handleTypedSubmit(event: React.FormEvent) {
    event.preventDefault();
    const text = draft;
    setDraft("");
    void submit(text);
  }

  return (
    <div className="hud-panel flex flex-col gap-2 p-3">
      <div className="flex items-center justify-between">
        <p className="hud-label text-[11px] text-text-primary">JARVIS · Executive Assistant</p>
        <span className="hud-label text-[10px] text-text-muted">
          {busy ? "thinking…" : speaking ? "speaking" : listening ? "listening" : "voice ready"}
        </span>
      </div>

      {turns.length > 0 && (
        <div ref={logRef} className="max-h-48 space-y-2 overflow-y-auto pr-1">
          {turns.map((turn, index) => (
            <p
              key={index}
              className={`whitespace-pre-wrap text-[12px] leading-relaxed ${
                turn.who === "you" ? "text-accent-cyan" : "text-text-primary"
              }`}
            >
              <span className="hud-label mr-2 text-[9px] text-text-muted">
                {turn.who === "you" ? "You" : "JARVIS"}
              </span>
              {turn.text}
            </p>
          ))}
        </div>
      )}

      {interim && <p className="text-[12px] italic text-text-muted">{interim}…</p>}

      <form onSubmit={handleTypedSubmit} className="flex items-center gap-2">
        <button
          type="button"
          onClick={listening ? stopListening : startListening}
          disabled={!supported}
          aria-label={listening ? "Stop listening" : "Start voice conversation"}
          title={
            supported
              ? listening
                ? "Stop listening"
                : "Talk to JARVIS"
              : "Voice input is not supported in this browser"
          }
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full border transition-colors ${
            listening
              ? "border-status-needs-review bg-status-needs-review/20 text-status-needs-review animate-pulse"
              : "border-accent-cyan/50 text-accent-cyan hover:bg-accent-cyan/10"
          } disabled:cursor-not-allowed disabled:opacity-40`}
        >
          <MicIcon />
        </button>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={listening ? "Listening — or type instead…" : "Ask or instruct JARVIS…"}
          className="min-w-0 flex-1 rounded border border-border bg-surface-raised px-3 py-2 text-[13px] text-text-primary outline-none placeholder:text-text-muted focus:border-accent-cyan/60"
        />
        <button
          type="submit"
          disabled={busy || !draft.trim()}
          className="rounded border border-accent-cyan/50 px-3 py-2 text-[12px] text-accent-cyan transition-colors hover:bg-accent-cyan/10 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Send
        </button>
      </form>
    </div>
  );
}

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" width={18} height={18} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10v1a7 7 0 0 0 14 0v-1" />
      <path d="M12 18v4M8 22h8" />
    </svg>
  );
}
