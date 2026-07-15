"use client";

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { createProject, searchProjects, type ProjectSearchHit } from "@/lib/api";
import { DEPARTMENTS } from "@/lib/orgTopology";
import { useOrgStore } from "@/store/orgStore";

type PaletteMode = "list" | "start-project" | "search-memory";

type CommandAction =
  | { kind: "navigate"; path: string }
  | { kind: "start-project" }
  | { kind: "search-memory" }
  | { kind: "disabled" };

interface Command {
  id: string;
  label: string;
  hint?: string;
  group: string;
  /** Extra terms matched by the filter box but not shown, so alternate
   * phrasings (e.g. "Show Timeline" for the Mission Control command)
   * are discoverable without cluttering the visible label. */
  keywords?: string[];
  disabled?: boolean;
  action: CommandAction;
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export function CommandPalette() {
  const router = useRouter();
  const agents = useOrgStore((state) => state.agents);

  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [mode, setMode] = useState<PaletteMode>("list");

  // Command list (filter box) state.
  const [filter, setFilter] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);

  // Start Project sub-mode state.
  const [goalInput, setGoalInput] = useState("");
  const [projectStartedMessage, setProjectStartedMessage] = useState<string | null>(null);

  // Search Memory sub-mode state.
  const [searchQuery, setSearchQuery] = useState("");
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<ProjectSearchHit[] | null>(null);
  const [selectedResultIndex, setSelectedResultIndex] = useState(0);

  const overlayRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const filterInputRef = useRef<HTMLInputElement>(null);
  const goalInputRef = useRef<HTMLInputElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const closeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const resetToList = () => {
    setMode("list");
    setFilter("");
    setSelectedIndex(0);
    setGoalInput("");
    setProjectStartedMessage(null);
    setSearchQuery("");
    setSearchResults(null);
    setSearchError(null);
    setSelectedResultIndex(0);
  };

  const closePalette = () => {
    setOpen(false);
  };

  // ---- Command list construction (always reflects live store data) ----
  const commands = useMemo<Command[]>(() => {
    const list: Command[] = [];

    list.push({
      id: "action-start-project",
      label: "Start Project",
      group: "Actions",
      action: { kind: "start-project" },
    });
    list.push({
      id: "action-search-memory",
      label: "Search Memory",
      group: "Actions",
      action: { kind: "search-memory" },
    });

    list.push({
      id: "nav-mission-control",
      label: "Switch to Mission Control",
      hint: "Timeline",
      group: "Navigate",
      keywords: ["Show Timeline", "home"],
      action: { kind: "navigate", path: "/" },
    });
    list.push({
      id: "nav-knowledge",
      label: "Switch to Knowledge Universe",
      group: "Navigate",
      keywords: ["knowledge", "memory graph"],
      action: { kind: "navigate", path: "/knowledge" },
    });

    for (const department of DEPARTMENTS) {
      list.push({
        id: `dept-${department.id}`,
        label: `Open Department: ${department.label}`,
        group: "Departments",
        action: { kind: "navigate", path: `/department/${department.id}` },
      });
    }

    const roster = Object.values(agents).sort((a, b) => a.role.localeCompare(b.role));
    for (const agent of roster) {
      list.push({
        id: `agent-${agent.role}`,
        label: `Inspect Agent: ${agent.role}`,
        hint: agent.department,
        group: "Agents",
        action: { kind: "navigate", path: `/department/${agent.department}` },
      });
    }

    list.push({
      id: "coming-soon-generate-report",
      label: "Generate Report",
      hint: "Coming soon",
      group: "Coming soon",
      disabled: true,
      action: { kind: "disabled" },
    });
    list.push({
      id: "coming-soon-replay-workflow",
      label: "Replay Workflow",
      hint: "Coming soon",
      group: "Coming soon",
      disabled: true,
      action: { kind: "disabled" },
    });

    return list;
  }, [agents]);

  const filteredCommands = useMemo(() => {
    const query = filter.trim().toLowerCase();
    if (!query) return commands;
    return commands.filter((command) => {
      const haystack = `${command.label} ${command.group} ${(command.keywords ?? []).join(" ")}`.toLowerCase();
      return haystack.includes(query);
    });
  }, [commands, filter]);

  function runCommand(command: Command) {
    if (command.disabled) return;
    switch (command.action.kind) {
      case "navigate":
        router.push(command.action.path);
        closePalette();
        break;
      case "start-project":
        setMode("start-project");
        break;
      case "search-memory":
        setMode("search-memory");
        break;
      case "disabled":
        break;
    }
  }

  function handleStartProjectSubmit(event: React.FormEvent) {
    event.preventDefault();
    const goal = goalInput.trim();
    if (!goal || projectStartedMessage) return;

    // Fire-and-forget: a real project run can take a long time (a dozen+
    // sequential/parallel LLM calls). The live SSE stream -- already wired
    // globally -- is what shows progress from here, not this response.
    createProject(goal).catch((error: unknown) => {
      console.error("createProject failed", error);
    });

    setProjectStartedMessage(`Started: "${goal}" -- watch the live event stream for progress.`);
    setGoalInput("");

    if (closeTimeoutRef.current) clearTimeout(closeTimeoutRef.current);
    closeTimeoutRef.current = setTimeout(() => {
      closePalette();
    }, 1100);
  }

  async function handleSearchMemorySubmit(event: React.FormEvent) {
    event.preventDefault();
    const query = searchQuery.trim();
    if (!query) return;

    setSearchLoading(true);
    setSearchError(null);
    try {
      const hits = await searchProjects(query, 5);
      setSearchResults(hits);
      setSelectedResultIndex(0);
    } catch (error) {
      setSearchResults(null);
      setSearchError(error instanceof Error ? error.message : "Search failed");
    } finally {
      setSearchLoading(false);
    }
  }

  function openSearchResult(hit: ProjectSearchHit) {
    router.push(`/knowledge?project=${encodeURIComponent(hit.id)}`);
    closePalette();
  }

  // ---- Global shortcut: Cmd+K / Ctrl+K opens (toggles), Escape steps back/closes ----
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const isModK = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";
      if (isModK) {
        event.preventDefault();
        if (open) {
          setOpen(false);
        } else {
          resetToList();
          setMounted(true);
          setOpen(true);
        }
        return;
      }

      if (!open) return;

      if (event.key === "Escape") {
        event.preventDefault();
        if (mode !== "list") {
          setMode("list");
        } else {
          closePalette();
        }
        return;
      }

      if (mode === "list") {
        if (event.key === "ArrowDown") {
          event.preventDefault();
          setSelectedIndex((index) => Math.min(index + 1, filteredCommands.length - 1));
        } else if (event.key === "ArrowUp") {
          event.preventDefault();
          setSelectedIndex((index) => Math.max(index - 1, 0));
        } else if (event.key === "Enter") {
          event.preventDefault();
          const command = filteredCommands[selectedIndex];
          if (command) runCommand(command);
        }
      } else if (mode === "search-memory" && searchResults && searchResults.length > 0) {
        if (event.key === "ArrowDown") {
          event.preventDefault();
          setSelectedResultIndex((index) => Math.min(index + 1, searchResults.length - 1));
        } else if (event.key === "ArrowUp") {
          event.preventDefault();
          setSelectedResultIndex((index) => Math.max(index - 1, 0));
        } else if (event.key === "Enter" && document.activeElement !== searchInputRef.current) {
          event.preventDefault();
          const hit = searchResults[selectedResultIndex];
          if (hit) openSearchResult(hit);
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, mode, filteredCommands, selectedIndex, searchResults, selectedResultIndex]);

  useEffect(() => {
    return () => {
      if (closeTimeoutRef.current) clearTimeout(closeTimeoutRef.current);
    };
  }, []);

  // Autofocus the relevant input whenever the palette opens or the mode changes.
  useEffect(() => {
    if (!open) return;
    const raf = requestAnimationFrame(() => {
      if (mode === "list") filterInputRef.current?.focus();
      else if (mode === "start-project") goalInputRef.current?.focus();
      else if (mode === "search-memory") searchInputRef.current?.focus();
    });
    return () => cancelAnimationFrame(raf);
  }, [open, mode]);

  // ---- Open/close fade+scale transition ----
  // `mounted` is flipped true the moment `open` becomes true (in the
  // keydown handler above, so the overlay/panel exist in the DOM before
  // this effect tries to animate them) and flipped back false once the
  // exit tween's onComplete fires below.
  useGSAP(
    () => {
      if (!mounted) return;
      const overlay = overlayRef.current;
      const panel = panelRef.current;
      if (!overlay || !panel) return;

      if (prefersReducedMotion()) {
        gsap.set(overlay, { opacity: open ? 1 : 0 });
        gsap.set(panel, { opacity: open ? 1 : 0, scale: 1, y: 0 });
        if (!open) setMounted(false);
        return;
      }

      if (open) {
        gsap.set(overlay, { opacity: 0 });
        gsap.set(panel, { opacity: 0, scale: 0.96, y: -8 });
        gsap.to(overlay, { opacity: 1, duration: 0.15, ease: "power2.out" });
        gsap.to(panel, { opacity: 1, scale: 1, y: 0, duration: 0.2, ease: "power3.out" });
      } else {
        gsap.to(overlay, { opacity: 0, duration: 0.12, ease: "power2.in" });
        gsap.to(panel, {
          opacity: 0,
          scale: 0.96,
          y: -8,
          duration: 0.15,
          ease: "power2.in",
          onComplete: () => setMounted(false),
        });
      }
    },
    { scope: overlayRef, dependencies: [open, mounted] }
  );

  if (!mounted) return null;

  let groupCursor = "";

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-start justify-center bg-void/70 backdrop-blur-sm px-4 pt-[12vh]"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) closePalette();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="glass-panel w-full max-w-xl overflow-hidden shadow-2xl"
      >
        {mode === "list" && (
          <>
            <div className="border-b border-border px-4 py-3">
              <input
                ref={filterInputRef}
                value={filter}
                onChange={(event) => {
                  setFilter(event.target.value);
                  setSelectedIndex(0);
                }}
                placeholder="Type a command..."
                aria-label="Search commands"
                role="combobox"
                aria-expanded="true"
                aria-controls="command-palette-list"
                aria-activedescendant={
                  filteredCommands[selectedIndex]
                    ? `command-option-${filteredCommands[selectedIndex].id}`
                    : undefined
                }
                className="w-full bg-transparent text-text-primary placeholder:text-text-muted outline-none text-sm"
              />
            </div>
            <ul
              id="command-palette-list"
              role="listbox"
              aria-label="Commands"
              className="max-h-96 overflow-y-auto py-2"
            >
              {filteredCommands.length === 0 && (
                <li className="px-4 py-6 text-center text-sm text-text-muted">
                  No matching commands.
                </li>
              )}
              {filteredCommands.map((command, index) => {
                const showGroupHeader = command.group !== groupCursor;
                groupCursor = command.group;
                const isSelected = index === selectedIndex;
                return (
                  <li key={command.id}>
                    {showGroupHeader && (
                      <div className="px-4 pt-2 pb-1 text-[11px] uppercase tracking-wide text-text-muted">
                        {command.group}
                      </div>
                    )}
                    <button
                      id={`command-option-${command.id}`}
                      role="option"
                      aria-selected={isSelected}
                      aria-disabled={command.disabled}
                      type="button"
                      disabled={command.disabled}
                      onMouseEnter={() => setSelectedIndex(index)}
                      onClick={() => runCommand(command)}
                      className={`flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm transition-colors ${
                        command.disabled
                          ? "cursor-not-allowed text-text-muted opacity-60"
                          : isSelected
                            ? "bg-accent-blue/20 text-text-primary"
                            : "text-text-secondary hover:bg-surface-raised"
                      }`}
                    >
                      <span>{command.label}</span>
                      {command.hint && (
                        <span className="text-xs text-text-muted">{command.hint}</span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
            <div className="flex items-center justify-between border-t border-border px-4 py-2 text-[11px] text-text-muted">
              <span>↑↓ navigate · Enter run · Esc close</span>
              <span>⌘K / Ctrl+K</span>
            </div>
          </>
        )}

        {mode === "start-project" && (
          <div className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium text-text-primary">Start Project</h2>
              <button
                type="button"
                onClick={() => setMode("list")}
                className="text-xs text-text-muted hover:text-text-secondary"
              >
                Back
              </button>
            </div>
            <form onSubmit={handleStartProjectSubmit} className="space-y-3">
              <input
                ref={goalInputRef}
                value={goalInput}
                onChange={(event) => setGoalInput(event.target.value)}
                placeholder="Describe the project goal..."
                aria-label="Project goal"
                className="w-full rounded border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none"
              />
              <button
                type="submit"
                disabled={!goalInput.trim() || Boolean(projectStartedMessage)}
                className="w-full rounded bg-accent-blue px-3 py-2 text-sm text-text-primary disabled:opacity-50"
              >
                Launch project
              </button>
            </form>
            {projectStartedMessage && (
              <p className="text-xs text-status-completed">{projectStartedMessage}</p>
            )}
          </div>
        )}

        {mode === "search-memory" && (
          <div className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium text-text-primary">Search Memory</h2>
              <button
                type="button"
                onClick={() => setMode("list")}
                className="text-xs text-text-muted hover:text-text-secondary"
              >
                Back
              </button>
            </div>
            <form onSubmit={handleSearchMemorySubmit} className="space-y-3">
              <input
                ref={searchInputRef}
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Search past projects..."
                aria-label="Search memory query"
                className="w-full rounded border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none"
              />
              <button
                type="submit"
                disabled={!searchQuery.trim() || searchLoading}
                className="w-full rounded bg-accent-blue px-3 py-2 text-sm text-text-primary disabled:opacity-50"
              >
                {searchLoading ? "Searching..." : "Search"}
              </button>
            </form>

            {searchError && <p className="text-xs text-status-needs_review">{searchError}</p>}

            {searchResults && searchResults.length === 0 && !searchError && (
              <p className="text-xs text-text-muted">No matching projects.</p>
            )}

            {searchResults && searchResults.length > 0 && (
              <ul role="listbox" aria-label="Search results" className="space-y-1">
                {searchResults.map((hit, index) => (
                  <li key={hit.id}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={index === selectedResultIndex}
                      onMouseEnter={() => setSelectedResultIndex(index)}
                      onClick={() => openSearchResult(hit)}
                      className={`w-full rounded px-3 py-2 text-left text-sm transition-colors ${
                        index === selectedResultIndex
                          ? "bg-accent-blue/20 text-text-primary"
                          : "text-text-secondary hover:bg-surface-raised"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium">{hit.goal ?? `Project ${hit.id}`}</span>
                        <span className="text-xs text-text-muted">
                          {hit.score.toFixed(2)}
                        </span>
                      </div>
                      {hit.summary && (
                        <p className="mt-0.5 text-xs text-text-muted line-clamp-2">
                          {hit.summary}
                        </p>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
