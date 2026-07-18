import { forwardRef, type ReactNode } from "react";

const POSITIONED = /\b(?:static|relative|absolute|fixed|sticky)\b/;

/**
 * Decorative corner brackets shared by every Mission Control panel -- the
 * "sci-fi HUD console" cue from the reference designs (bracket-cornered
 * cards rather than plain rounded rectangles). Purely visual: it wraps
 * children in a positioned container (so the bracket spans have something
 * to anchor to) and layers four absolutely-positioned bracket spans over
 * them, never affecting layout or interaction.
 *
 * Callers that need real `absolute`/`fixed` placement (PromptBar,
 * ExecutionLogPanel, PreviewPanel...) pass that in `className` themselves --
 * `relative` is only added as a fallback when the caller hasn't already set
 * a position utility. Tailwind's `.relative` and `.absolute` utilities have
 * equal specificity, so if both landed on the same element the one later in
 * Tailwind's generated stylesheet would silently win regardless of which
 * one the caller intended, turning an "absolute" floating panel back into
 * a normal in-flow block.
 *
 * Forwards its ref to the wrapping div so a caller (PromptBar's mission-
 * start glow pulse, e.g.) can animate the frame itself with GSAP without
 * this component needing to know anything about that animation.
 */
export const HudFrame = forwardRef<HTMLDivElement, { children: ReactNode; className?: string }>(
  function HudFrame({ children, className = "" }, ref) {
    const positionClass = POSITIONED.test(className) ? "" : "relative ";
    return (
      <div ref={ref} className={`${positionClass}${className}`}>
        <span className="pointer-events-none absolute -left-px -top-px h-3 w-3 border-l-2 border-t-2 border-accent-cyan/70" />
        <span className="pointer-events-none absolute -right-px -top-px h-3 w-3 border-r-2 border-t-2 border-accent-cyan/70" />
        <span className="pointer-events-none absolute -bottom-px -left-px h-3 w-3 border-b-2 border-l-2 border-accent-cyan/70" />
        <span className="pointer-events-none absolute -bottom-px -right-px h-3 w-3 border-b-2 border-r-2 border-accent-cyan/70" />
        {children}
      </div>
    );
  }
);
