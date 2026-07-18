/** Shared across every GSAP-driven component (CommandPalette,
 * NotificationStack, HudSidebar, PromptBar, ...) so "respect the OS-level
 * reduced-motion preference" is one real check, not N copies drifting
 * apart. Animations in this app communicate state (a mission starting,
 * a notification arriving) -- when the user has asked for reduced motion,
 * every one of those components snaps to its end state instead of
 * skipping the state change entirely. */
export function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}
