"""Cooperative mission cancellation -- see orchestration/cancellation.py.

The critical property under test: once a cancel is requested for a
project_id, `run_organization` must raise before making even one more LLM
call. `ExplodingClient.complete` asserts if it's ever invoked, so these
tests prove "stops spending tokens", not just "eventually returns" -- with
zero real network calls, matching the project's cost-free test conventions.
"""

import uuid

import pytest

from aio.events.bus import event_bus
from aio.orchestration import cancellation
from aio.orchestration.cancellation import MissionCancelled
from aio.orchestration.graph import run_organization


class ExplodingClient:
    def complete(self, system: str, user: str, max_tokens: int = 2048) -> str:
        raise AssertionError("LLM call made after cancellation was requested")


def test_registry_roundtrip():
    project_id = str(uuid.uuid4())
    assert cancellation.is_cancelled(project_id) is False
    cancellation.register(project_id)
    assert cancellation.is_cancelled(project_id) is False
    assert cancellation.request_cancel(project_id) is True
    assert cancellation.is_cancelled(project_id) is True
    cancellation.clear(project_id)
    assert cancellation.is_cancelled(project_id) is False


def test_register_is_idempotent_and_does_not_clear_a_pending_cancel():
    """Guards the exact race api/main.py's create_project relies on: the
    HTTP handler registers synchronously before returning project_id to the
    caller, then run_organization registers again once its background
    thread starts -- the second call must not reset an already-set Event."""
    project_id = str(uuid.uuid4())
    cancellation.register(project_id)
    cancellation.request_cancel(project_id)
    cancellation.register(project_id)  # second, later registration
    assert cancellation.is_cancelled(project_id) is True
    cancellation.clear(project_id)


def test_request_cancel_on_unknown_project_returns_false():
    assert cancellation.request_cancel(str(uuid.uuid4())) is False


def test_run_organization_stops_at_the_first_agent_boundary_once_cancelled():
    project_id = str(uuid.uuid4())
    cancellation.register(project_id)
    cancellation.request_cancel(project_id)

    with pytest.raises(MissionCancelled):
        run_organization(
            goal="Launch a clinic scheduling tool",
            llm=ExplodingClient(),
            persist=False,
            swarm=False,
            project_id=project_id,
        )

    cancelled_events = [
        e
        for e in event_bus.recent(50)
        if e.project_id == project_id and e.type == "workflow_cancelled"
    ]
    assert len(cancelled_events) == 1

    # The registry entry is cleaned up once the run unwinds -- a second
    # cancel request against the same (now-finished) id should report
    # "not found", not silently succeed.
    assert cancellation.request_cancel(project_id) is False
