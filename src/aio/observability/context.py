"""Implicit per-run correlation ID.

`run_organization` generates a project_id *before* the graph starts (not
just at the final `save_project` call, as in Phase 2) so that every event
published during the run -- by any agent, on any node -- can be tagged
with it. Threading a `project_id` parameter through every agent method
signature (`execute(goal, project_id=...)` on all 8+ agents) would be a
lot of cross-cutting-concern churn for what is fundamentally an
observability correlation ID, so it's carried via a contextvar instead:
set once at the top of `run_organization`, read implicitly by
`Agent._log`/`run_logged` wherever they're called in that same call stack.
"""

from __future__ import annotations

import contextvars

current_project_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_project_id", default=None
)
