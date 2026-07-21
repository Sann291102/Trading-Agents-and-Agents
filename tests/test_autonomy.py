"""JARVIS's autonomous executive loop -- the thinking/acting half.

Only `aio.os.autonomy` and the kernel's settings surface are exercised here.
The kernel's asyncio scheduling is deliberately untested: there is nothing
worth asserting about `asyncio.sleep`, and a test that waits on a real
interval is a slow test that proves nothing.
"""

from __future__ import annotations

import json
import sys
import types

import pytest
from pydantic import BaseModel

from aio.actions.base import ActionContext, ActionOutcome, ActionResult, ActionRisk
from aio.actions.registry import _REGISTRY, action
from aio.business import BusinessService
from aio.events.bus import event_bus
from aio.models.autonomy import AutonomyDecision, AutonomySettings
from aio.os.autonomy import plan_next_actions, run_cycle
from aio.os.kernel import ExecutiveBrain

NOTE_ACTION = "autonomy_test_note"
ANNOUNCE_ACTION = "autonomy_test_announce"

_PERFORMED: list[str] = []


class _NoteParams(BaseModel):
    text: str


@pytest.fixture(autouse=True)
def connectors_present():
    """`available_actions()` (and therefore the planner catalog) imports
    `aio.connectors.connector_available`. Stub it only when the real module
    is absent, so this suite does not depend on connector wiring landing
    first and picks up the real implementation the moment it exists."""
    try:
        import aio.connectors  # noqa: F401
    except ImportError:
        module = types.ModuleType("aio.connectors")
        module.connector_available = lambda name: True  # type: ignore[attr-defined]
        sys.modules["aio.connectors"] = module
        yield
        sys.modules.pop("aio.connectors", None)
    else:
        yield


@pytest.fixture(autouse=True)
def test_actions():
    """Throwaway actions covering both risk levels.

    Registered and removed per test rather than declared at module scope:
    the registry is a process-global, and leaving fixtures in it would leak
    into any other suite that asserts on the real catalog. The registry has
    no public unregister, hence reaching into `_REGISTRY` here.
    """

    @action(
        NOTE_ACTION,
        description="File an internal note",
        risk=ActionRisk.SAFE,
        params_model=_NoteParams,
    )
    def _note(context: ActionContext, params: _NoteParams) -> ActionResult:
        _PERFORMED.append(params.text)
        return ActionResult(
            outcome=ActionOutcome.EXECUTED, summary=f"Filed a note: {params.text}"
        )

    @action(
        ANNOUNCE_ACTION,
        description="Publish an announcement to customers",
        risk=ActionRisk.SENSITIVE,
        params_model=_NoteParams,
    )
    def _announce(context: ActionContext, params: _NoteParams) -> ActionResult:
        _PERFORMED.append("ANNOUNCED")
        return ActionResult(outcome=ActionOutcome.EXECUTED, summary="Published")

    yield
    _PERFORMED.clear()
    _REGISTRY.pop(NOTE_ACTION, None)
    _REGISTRY.pop(ANNOUNCE_ACTION, None)


@pytest.fixture()
def service() -> BusinessService:
    svc = BusinessService(database_url="sqlite:///:memory:")
    svc.init_schema()
    return svc


@pytest.fixture()
def context_factory(service: BusinessService):
    return lambda: ActionContext(business=service, actor="JARVIS")


class FakeLLM:
    """Returns a canned decision and keeps the prompt it was handed, so the
    grounding of the planner prompt can be asserted."""

    def __init__(self, decision: dict) -> None:
        self._decision = decision
        self.system = ""
        self.user = ""

    def complete(self, system: str, user: str, max_tokens: int = 2048) -> str:
        self.system = system
        self.user = user
        return json.dumps(self._decision)


class BrokenLLM:
    def complete(self, system: str, user: str, max_tokens: int = 2048) -> str:
        raise RuntimeError("provider is down")


def _decision(*actions: dict) -> dict:
    return {
        "confidence": 0.8,
        "reasoning_summary": "Cheapest step toward launch.",
        "observation": "TradeW is pre-revenue with no milestones recorded.",
        "actions": list(actions),
    }


def _new_events(before_ids: set[str], event_type: str) -> list:
    return [e for e in event_bus.recent(300) if e.id not in before_ids and e.type == event_type]


def _event_ids() -> set[str]:
    return {e.id for e in event_bus.recent(300)}


# -- executing ------------------------------------------------------------


def test_safe_action_is_executed_and_recorded(service, context_factory):
    llm = FakeLLM(
        _decision(
            {
                "action": NOTE_ACTION,
                "params": {"text": "Broker API is the critical path"},
                "rationale": "Nothing is written down yet.",
                "confidence": 0.9,
            }
        )
    )

    results = run_cycle(service, context_factory=context_factory, llm=llm, limit=2)

    assert [r.outcome for r in results] == [ActionOutcome.EXECUTED]
    assert _PERFORMED == ["Broker API is the critical path"]
    runs = service.list_action_runs()
    assert [run.action for run in runs] == [NOTE_ACTION]
    assert runs[0].outcome == "executed"
    assert runs[0].actor == "JARVIS"


def test_recorded_runs_feed_the_next_cycles_prompt(service, context_factory):
    """The 'Learn' half of the loop: without its own history in the prompt
    the planner re-proposes the same action forever."""
    llm = FakeLLM(_decision({"action": NOTE_ACTION, "params": {"text": "First pass"}}))
    run_cycle(service, context_factory=context_factory, llm=llm, limit=1)

    plan_next_actions(service, llm, limit=1)
    assert "First pass" in llm.user
    assert "do not repeat" in llm.user.lower()


# -- skipping -------------------------------------------------------------


def test_unknown_action_is_skipped_without_raising(service, context_factory):
    """The planner is an LLM, so invented action names are expected input,
    not an exceptional condition."""
    llm = FakeLLM(
        _decision(
            {"action": "send_rocket_to_mars", "params": {}},
            {"action": NOTE_ACTION, "params": {"text": "Still ran"}},
        )
    )

    results = run_cycle(service, context_factory=context_factory, llm=llm, limit=2)

    assert [r.outcome for r in results] == [ActionOutcome.EXECUTED]
    assert _PERFORMED == ["Still ran"]
    assert [run.action for run in service.list_action_runs()] == [NOTE_ACTION]


def test_planner_failure_costs_one_cycle_not_the_loop(service, context_factory):
    results = run_cycle(service, context_factory=context_factory, llm=BrokenLLM(), limit=2)
    assert results == []
    assert service.list_action_runs() == []


def test_unparseable_response_is_survivable(service, context_factory):
    class GarbageLLM:
        def complete(self, system: str, user: str, max_tokens: int = 2048) -> str:
            return "I think we should probably consider launching soon."

    assert run_cycle(service, context_factory=context_factory, llm=GarbageLLM(), limit=2) == []


# -- escalating -----------------------------------------------------------


def test_sensitive_action_is_parked_for_approval(service, context_factory):
    """The autonomy rule: outward-facing work never runs straight from the
    loop, it becomes an executable Approval the founder decides on."""
    llm = FakeLLM(
        _decision({"action": ANNOUNCE_ACTION, "params": {"text": "We are live"}})
    )

    results = run_cycle(service, context_factory=context_factory, llm=llm, limit=2)

    assert [r.outcome for r in results] == [ActionOutcome.ESCALATED]
    assert "ANNOUNCED" not in _PERFORMED

    pending = service.list_approvals(status="pending")
    assert len(pending) == 1
    assert pending[0].pending_action == ANNOUNCE_ACTION
    assert pending[0].is_executable
    assert json.loads(pending[0].pending_params_json) == {"text": "We are live"}


# -- idling ---------------------------------------------------------------


def test_empty_action_list_is_a_valid_no_op_cycle(service, context_factory):
    """Idling must be allowed -- a loop forced to always act invents work."""
    llm = FakeLLM(_decision())

    before = _event_ids()
    results = run_cycle(service, context_factory=context_factory, llm=llm, limit=2)

    assert results == []
    assert service.list_action_runs() == []
    cycle_events = _new_events(before, "autonomy_cycle")
    assert len(cycle_events) == 1
    assert "nothing worth doing" in cycle_events[0].message


def test_cycle_publishes_exactly_one_autonomy_event(service, context_factory):
    llm = FakeLLM(_decision({"action": NOTE_ACTION, "params": {"text": "one"}}))

    before = _event_ids()
    run_cycle(service, context_factory=context_factory, llm=llm, limit=2)

    cycle_events = _new_events(before, "autonomy_cycle")
    assert len(cycle_events) == 1
    assert cycle_events[0].payload["executed"] == 1
    assert cycle_events[0].payload["observation"].startswith("TradeW is pre-revenue")


# -- prioritising ---------------------------------------------------------


def test_limit_is_enforced_on_the_response_not_just_the_prompt(service, context_factory):
    """A model that ignores the instruction and returns three actions must
    not get three actions' worth of authority."""
    llm = FakeLLM(
        _decision(
            {"action": NOTE_ACTION, "params": {"text": "one"}},
            {"action": NOTE_ACTION, "params": {"text": "two"}},
            {"action": NOTE_ACTION, "params": {"text": "three"}},
        )
    )

    results = run_cycle(service, context_factory=context_factory, llm=llm, limit=1)

    assert len(results) == 1
    assert _PERFORMED == ["one"]


def test_planner_prompt_is_grounded_in_state_history_and_catalog(service):
    llm = FakeLLM(_decision())

    decision = plan_next_actions(service, llm, limit=2)

    assert isinstance(decision, AutonomyDecision)
    assert "TradeW" in llm.user  # observed state
    assert "No actions taken yet." in llm.user  # its own history
    assert NOTE_ACTION in llm.user  # what it may do
    assert "sensitive" in llm.user  # risk travels with the catalog entry
    assert llm.system.startswith("You are the Autonomous Operator,")
    assert "verbatim" in llm.system


def test_planner_never_offers_pre_approval(service, context_factory):
    """Regression guard on the loop's core safety property: a sensitive
    action reached through the loop escalates, never executes."""
    llm = FakeLLM(_decision({"action": ANNOUNCE_ACTION, "params": {"text": "x"}}))
    run_cycle(service, context_factory=context_factory, llm=llm, limit=1)
    assert [run.outcome for run in service.list_action_runs()] == ["escalated"]


# -- kernel settings ------------------------------------------------------


def test_autonomy_is_disabled_on_a_fresh_install():
    """JARVIS must not act on someone's company until they switch it on."""
    defaults = AutonomySettings()
    assert defaults.enabled is False
    assert defaults.interval_seconds == 900
    assert defaults.max_actions_per_cycle == 2
    assert ExecutiveBrain().get_settings().enabled is False


def test_settings_update_is_partial_and_revalidated():
    brain = ExecutiveBrain()

    updated = brain.update_settings(enabled=True)
    assert updated.enabled is True
    assert updated.interval_seconds == 900  # untouched fields survive

    with pytest.raises(Exception):
        brain.update_settings(interval_seconds=1)  # below the guard rail
    assert brain.get_settings().interval_seconds == 900


def test_settings_accept_a_model_or_a_dict():
    brain = ExecutiveBrain()
    assert brain.update_settings({"max_actions_per_cycle": 3}).max_actions_per_cycle == 3
    assert brain.update_settings(AutonomySettings(enabled=True)).enabled is True


def test_get_settings_returns_a_copy():
    brain = ExecutiveBrain()
    snapshot = brain.get_settings()
    snapshot.enabled = True
    assert brain.get_settings().enabled is False


def test_unconfigured_kernel_does_not_crash_a_cycle():
    """The kernel is constructed at import time, before app state exists."""
    assert ExecutiveBrain().run_once() == []


def test_configured_kernel_runs_a_cycle(service, context_factory, monkeypatch):
    llm = FakeLLM(_decision({"action": NOTE_ACTION, "params": {"text": "kernel-driven"}}))
    # run_cycle imports build_default_llm lazily, so patching the source
    # module is what reaches the kernel's own (llm-less) call path.
    monkeypatch.setattr("aio.llm.build_default_llm", lambda: llm)

    brain = ExecutiveBrain()
    brain.configure(lambda: service, context_factory)
    assert brain.is_configured

    results = brain.run_once()
    assert [r.outcome for r in results] == [ActionOutcome.EXECUTED]
    assert brain.cycles_run == 1
    assert _PERFORMED == ["kernel-driven"]


def test_kernel_run_once_ignores_the_enabled_switch(service, context_factory, monkeypatch):
    """`enabled` gates JARVIS acting unprompted. The founder pressing 'run
    now' is a direct instruction and must work with autonomy switched off."""
    llm = FakeLLM(_decision({"action": NOTE_ACTION, "params": {"text": "on demand"}}))
    monkeypatch.setattr("aio.llm.build_default_llm", lambda: llm)

    brain = ExecutiveBrain()
    brain.configure(lambda: service, context_factory)
    assert brain.get_settings().enabled is False

    assert len(brain.run_once()) == 1
