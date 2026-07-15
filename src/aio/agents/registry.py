"""Registry of every implemented agent, built by walking `Agent` subclasses.

This is what makes "future agents automatically appear in the UI" true:
adding a new department means writing a new `Agent` subclass with `role`
and `department` set -- which you have to do anyway for it to exist and do
anything -- not a second, separate manual registration step. By the time
this module's body runs, every concrete agent has already been imported:
`aio.agents.registry` is a submodule of the `aio.agents` package, and
Python always fully executes a package's `__init__.py` (which imports
every concrete agent class) before running any of its submodules.

`GET /agents` in api/main.py serves `all_agent_classes()` plus each role's
live status from `agent_status_tracker`.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace

from aio.agents.base import Agent
from aio.events.bus import OrgEvent, event_bus


def all_agent_classes() -> list[type[Agent]]:
    """Every concrete Agent subclass that overrides `role` (skips `Agent`
    itself and, defensively, any subclass that forgot to set one)."""
    seen: dict[str, type[Agent]] = {}
    stack = list(Agent.__subclasses__())
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        if cls.role != Agent.role:
            seen[cls.role] = cls
    return list(seen.values())


@dataclass
class AgentStatus:
    role: str
    department: str
    status: str = "idle"
    last_confidence: float | None = None
    last_duration_seconds: float | None = None
    last_project_id: str | None = None
    last_message: str = ""


class AgentStatusTracker:
    """Live status per agent role, derived *only* from real
    agent_started/agent_finished events on the shared event bus -- never
    polled, never guessed, never advanced by a timer.

    Deliberately does not attempt to derive a "waiting" (queued but not yet
    reached) state: that requires knowing the orchestration graph's shape,
    which this per-role event tally has no visibility into. The frontend
    already needs to know the graph topology to render the live workflow
    diagram, so it derives "waiting" itself (any node downstream of the
    currently-active one) rather than this tracker inventing a status it
    can't actually justify from data.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._statuses: dict[str, AgentStatus] = {
            cls.role: AgentStatus(role=cls.role, department=cls.department)
            for cls in all_agent_classes()
        }
        event_bus.add_listener(self._on_event)

    def _on_event(self, event: OrgEvent) -> None:
        if event.type not in ("agent_started", "agent_finished") or event.agent_role is None:
            return
        with self._lock:
            current = self._statuses.get(event.agent_role) or AgentStatus(
                role=event.agent_role, department=event.department or "General"
            )
            if event.type == "agent_started":
                current = replace(
                    current,
                    status="executing",
                    last_project_id=event.project_id,
                    last_message=event.message,
                )
            else:
                has_error = bool(event.payload.get("error"))
                current = replace(
                    current,
                    status="needs_review" if has_error else "completed",
                    last_confidence=event.confidence,
                    last_duration_seconds=event.duration_seconds,
                    last_project_id=event.project_id,
                    last_message=event.message,
                )
            self._statuses[event.agent_role] = current

    def snapshot(self) -> list[AgentStatus]:
        with self._lock:
            return list(self._statuses.values())


agent_status_tracker = AgentStatusTracker()
