"""Cooperative cancellation for an in-flight `run_organization` call.

`POST /projects` kicks off `run_organization` on a background thread (see
api/main.py) -- there's no `asyncio.Task` to `.cancel()` and no LangGraph
interrupt/checkpointer wired in, so "stop this mission" can only mean
"stop making further LLM calls the next time an agent boundary is reached".
A `threading.Event` per project_id, checked at each `Agent.run_logged`/
`run_logged_json` call site (see agents/base.py) right before the
token-costing LLM call, is the cheapest mechanism that actually saves spend
-- no LangGraph internals need to change.

Module-level dict, not a class instance threaded through every call site,
for the same reason `current_project_id` (observability/context.py) is a
contextvar rather than a parameter: this is a cross-cutting concern, not
part of any agent's real interface.
"""

from __future__ import annotations

import threading

_events: dict[str, threading.Event] = {}
_lock = threading.Lock()


def register(project_id: str) -> None:
    """Idempotent: `api/main.py` registers synchronously before returning
    `project_id` to the caller (so a cancel request can never race ahead of
    registration), and `run_organization` registers again once its
    background thread actually starts. The second call must not replace an
    already-`.set()` Event with a fresh unset one -- `setdefault` keeps
    whichever Event was created first."""
    with _lock:
        _events.setdefault(project_id, threading.Event())


def request_cancel(project_id: str) -> bool:
    """Returns False if `project_id` isn't a currently-running mission
    (already finished, or never started) -- the caller uses this to decide
    whether to report 404 vs. "cancel requested"."""
    with _lock:
        event = _events.get(project_id)
    if event is None:
        return False
    event.set()
    return True


def is_cancelled(project_id: str | None) -> bool:
    if project_id is None:
        return False
    with _lock:
        event = _events.get(project_id)
    return event.is_set() if event else False


def clear(project_id: str) -> None:
    with _lock:
        _events.pop(project_id, None)


class MissionCancelled(Exception):
    """Raised at the next agent boundary after a cancel was requested,
    instead of spending another LLM call."""
