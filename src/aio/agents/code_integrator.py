from __future__ import annotations

from aio.agents.parsing import parse_delimited_files
from aio.models.preview import GeneratedApp
from aio.models.swarm import SwarmTaskResult

from .base import Agent


def _excerpt(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


_FILE_FORMAT_INSTRUCTION = (
    "Respond with ONLY the files, each preceded by its own marker line "
    "exactly in this form (no markdown fences, no commentary before, "
    "between, or after them):\n\n"
    "===FILE: app/page.tsx===\n"
    "<full file content>\n"
    "===FILE: components/Widget.tsx===\n"
    "<full file content>\n"
    "===END===\n\n"
    "Hard constraints:\n"
    "- The FIRST file you write MUST be named exactly `app/page.tsx` -- not "
    "`index.html`, not `demo.html`, not any other name. This is a Next.js "
    "App Router project, not a static HTML page: `app/page.tsx` is a React "
    "component (a `.tsx` function starting with `export default function "
    "Page()`), never raw `<!DOCTYPE html>` markup. If you are tempted to "
    "write a self-contained HTML demo file instead, don't -- rebuild that "
    "same idea as a React component at `app/page.tsx` instead. A response "
    "with no `app/page.tsx` file is a failed response.\n"
    "- At most 2 additional files, each under `components/*.tsx` or "
    "`lib/*.ts`.\n"
    "- Plain CSS via inline `style={{...}}` only -- no Tailwind, no CSS "
    "framework, no separate .css files (none are wired up).\n"
    "- Only import from `next`, `react`, `react-dom`, or relative paths to "
    "your own other generated files -- no other npm package is installed, "
    "including things that might feel natural for a \"live\" or "
    "\"real-time\" feature (socket.io, axios, chart/date libraries, icon "
    "packs, etc). If the demo calls for live-feeling data, simulate it "
    "with React state and `setInterval`/`useEffect`, not a real "
    "connection.\n"
    "- Never write `package.json`, `next.config.*`, `tsconfig.json`, or "
    "`app/layout.tsx` -- those already exist and are not yours to change.\n"
    "- This is a client-viewable demo, not production code: keep it "
    "self-contained, no external API calls, no environment variables."
)


class CodeIntegratorAgent(Agent):
    """Engineering Division. The final swarm-stage step: reads the approved
    tech plan plus every specialist's free-text output and synthesizes them
    into a small, runnable Next.js page -- the thing that actually becomes
    the live preview, instead of another block of prose. Deliberately
    scoped to at most 3 files (see _FILE_FORMAT_INSTRUCTION) for reliability
    over completeness; the goal is a genuine, working preview, not a full
    reproduction of the tech plan."""

    role = "Code Integrator"
    department = "Engineering"
    system_prompt = (
        "You are the Code Integrator on the Engineering team, the final "
        "step of the engineering swarm. You receive the approved technical "
        "plan and the outputs of every specialist who worked on it, and "
        "your job is to turn that into ONE small, genuinely runnable "
        "Next.js (App Router) page that demonstrates the core of what was "
        "designed -- not a full implementation, a focused, working "
        "demo.\n\n" + _FILE_FORMAT_INSTRUCTION
    )

    def execute(
        self, goal: str, tech_plan: str, swarm_results: list[SwarmTaskResult]
    ) -> GeneratedApp:
        # Real specialist outputs run 50-70k chars of elaborate, opinionated
        # architecture (React SPAs with Zustand, WebSocket integration,
        # multi-service designs) -- fed in full, that volume of detail
        # reliably pulls the model toward reproducing THAT architecture
        # rather than following the single-page-with-3-files-max format
        # below (confirmed: identical prompt, full-length inputs, three
        # different real runs each produced a different wrong structure --
        # a standalone HTML file, a Vite/CRA `src/App.tsx` tree, and a
        # zero-file response -- while a short, minimal version of the same
        # context reliably produced `app/page.tsx` on the first try).
        # Excerpts, not full text: enough flavor for a focused demo, not
        # enough detail to compete with the format instruction.
        tech_plan_excerpt = _excerpt(tech_plan, 1200)
        specialist_sections = "\n\n".join(
            f"### {result.role}\nTask: {result.task}\n\n"
            + (f"ERROR: {result.error}" if result.error else _excerpt(result.output, 400))
            for result in swarm_results
        )
        task = (
            f"Business goal:\n{goal}\n\n"
            f"Approved technical plan (excerpt):\n{tech_plan_excerpt}\n\n"
            f"Specialist outputs (excerpts, for flavor -- do not try to "
            f"reproduce their full architecture, stay within the file "
            f"format and constraints above):\n\n{specialist_sections}\n\n"
            "Produce the preview files now."
        )
        text, _ = self.run_logged(task, handoff_target=None)
        # Matches the "page + at most 2 more" cap stated in the prompt --
        # the writer's path allowlist is the hard backstop regardless, but
        # this keeps the parser's own limit honest with what was asked for.
        files = parse_delimited_files(text, max_files=3)
        return GeneratedApp(files=files)
