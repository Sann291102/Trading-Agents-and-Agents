"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { DEPARTMENTS } from "@/lib/orgTopology";
import { useOrgStore } from "@/store/orgStore";

const CONNECTION_LABEL: Record<string, string> = {
  open: "Live",
  connecting: "Connecting",
  closed: "Disconnected",
};

const CONNECTION_COLOR: Record<string, string> = {
  open: "bg-status-completed",
  connecting: "bg-status-executing",
  closed: "bg-status-needs-review",
};

function openCommandPalette() {
  // CommandPalette listens globally for Cmd/Ctrl+K -- dispatching the same
  // key event it already handles keeps this button as a thin trigger for
  // that one real code path instead of a second, parallel open mechanism.
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }));
}

/**
 * Slim fixed left nav rail -- the Sureflow-style "sidebar of destinations"
 * cue. Every link routes to a page that already exists (Mission Control,
 * Knowledge Universe, each real department from DEPARTMENTS); nothing here
 * is a placeholder. The bottom dot mirrors StatusBar's real SSE
 * connectionStatus so the rail also doubles as an always-visible heartbeat.
 */
export function HudSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const connectionStatus = useOrgStore((state) => state.connectionStatus);

  function handleLogout() {
    useOrgStore.getState().setToken(null);
    router.push("/login");
  }

  return (
    <nav
      aria-label="Mission Control navigation"
      className="hud-panel pointer-events-auto fixed left-0 top-0 bottom-10 z-20 flex w-16 flex-col items-center gap-1 py-4"
    >
      <div
        className="mb-3 flex h-8 w-8 items-center justify-center rounded-full border border-accent-cyan/50 text-[10px] font-bold text-accent-cyan"
        style={{ boxShadow: "var(--glow-cyan)" }}
        aria-hidden="true"
      >
        AI
      </div>

      <SidebarLink href="/" label="Mission Control" active={pathname === "/"}>
        <HomeIcon />
      </SidebarLink>
      <SidebarLink href="/knowledge" label="Knowledge Universe" active={pathname === "/knowledge"}>
        <GraphIcon />
      </SidebarLink>
      <SidebarLink href="/brain" label="The Brain" active={pathname === "/brain"}>
        <BrainIcon />
      </SidebarLink>

      <div className="my-2 h-px w-8 bg-border" aria-hidden="true" />

      {DEPARTMENTS.filter((department) => department.id !== "Executive").map((department) => (
        <SidebarLink
          key={department.id}
          href={`/department/${department.id}`}
          label={department.label}
          active={pathname === `/department/${department.id}`}
        >
          <span className="text-[9px] font-bold">{department.label.slice(0, 2).toUpperCase()}</span>
        </SidebarLink>
      ))}

      <button
        type="button"
        onClick={openCommandPalette}
        aria-label="Open command palette"
        title="Command palette (⌘K)"
        className="mt-2 flex h-10 w-10 items-center justify-center rounded text-text-muted transition-colors hover:bg-surface-raised hover:text-accent-cyan"
      >
        <SearchIcon />
      </button>

      <button
        type="button"
        onClick={handleLogout}
        aria-label="Log out"
        title="Log out"
        className="mt-1 flex h-10 w-10 items-center justify-center rounded text-text-muted transition-colors hover:bg-status-needs-review/10 hover:text-status-needs_review"
      >
        <LogoutIcon />
      </button>

      <div className="mt-auto flex flex-col items-center gap-1 pt-2">
        <span
          className={`h-2 w-2 rounded-full ${CONNECTION_COLOR[connectionStatus]}`}
          aria-hidden="true"
        />
        <span className="hud-label text-center text-[8px] leading-tight text-text-muted">
          {CONNECTION_LABEL[connectionStatus]}
        </span>
      </div>
    </nav>
  );
}

function SidebarLink({
  href,
  label,
  active,
  children,
}: {
  href: string;
  label: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-label={label}
      aria-current={active ? "page" : undefined}
      title={label}
      className={`flex h-10 w-10 items-center justify-center rounded transition-colors ${
        active
          ? "bg-accent-cyan/15 text-accent-cyan"
          : "text-text-muted hover:bg-surface-raised hover:text-text-primary"
      }`}
      style={active ? { boxShadow: "var(--glow-cyan)" } : undefined}
    >
      {children}
    </Link>
  );
}

function HomeIcon() {
  return (
    <svg viewBox="0 0 24 24" width={16} height={16} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 11l9-8 9 8" />
      <path d="M5 10v10h14V10" />
    </svg>
  );
}

function GraphIcon() {
  return (
    <svg viewBox="0 0 24 24" width={16} height={16} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="5" r="2" />
      <circle cx="5" cy="19" r="2" />
      <circle cx="19" cy="19" r="2" />
      <path d="M12 7v6M12 13l-5.5 4M12 13l5.5 4" />
    </svg>
  );
}

function BrainIcon() {
  return (
    <svg viewBox="0 0 24 24" width={16} height={16} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9 4a3 3 0 0 0-3 3 3 3 0 0 0-1.5 5.6A3 3 0 0 0 6 18a3 3 0 0 0 3 3" />
      <path d="M15 4a3 3 0 0 1 3 3 3 3 0 0 1 1.5 5.6A3 3 0 0 1 18 18a3 3 0 0 1-3 3" />
      <path d="M9 4v14M15 4v14" />
    </svg>
  );
}

function LogoutIcon() {
  return (
    <svg viewBox="0 0 24 24" width={16} height={16} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="M16 17l5-5-5-5" />
      <path d="M21 12H9" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" width={16} height={16} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-4.35-4.35" />
    </svg>
  );
}
