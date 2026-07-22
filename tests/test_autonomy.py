"""JARVIS's autonomous executive loop -- the thinking/acting half.

Only `aio.os.autonomy` and the kernel's settings surface are exercised here.
The kernel's asyncio scheduling is deliberately untested: there is nothing
worth asserting about `asyncio.sleep`, and a test that waits on a real
interval is a slow test that proves nothing.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import types

import pytest
from pydantic import BaseModel

from aio.actions.base import ActionContext, ActionOutcome, ActionResult, ActionRisk
from aio.actions.registry import _REGISTRY, action
from aio.business import BusinessService
from aio.events.bus import event_bus
from aio.models.autonomy import AutonomyDecision, AutonomySettings
from aio.models.signals import Signal
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


WEBHOOK_TITLE = "Stripe webhook has been failing"


def _signal(**overrides) -> Signal:
    data = {
        "source": "autonomy_test_eyes",
        "kind": "test_condition",
        "title": WEBHOOK_TITLE,
        "dedupe_key": "autonomy-test:webhook",
        "severity": "urgent",
    }
    data.update(overrides)
    return Signal(**data)


@pytest.fixture()
def fake_observer():
    """One pair of eyes that always sees the same thing.

    Registered per test and removed again: the observer registry is a
    process-global like the action registry, and a fake left in it would
    follow every later suite around.
    """
    from aio.observers.base import _REGISTRY as _OBSERVERS, Observer, register_observer

    class _Eyes(Observer):
        name = "autonomy_test_eyes"
        display_name = "Test Eyes"
        description = "Sees one fixed condition"
        watches = ("test_condition",)

        def __init__(self) -> None:
            self.calls = 0

        def observe(self, business) -> list[Signal]:
            self.calls += 1
            return [_signal()]

    eyes = _Eyes()
    register_observer(eyes)
    yield eyes
    _OBSERVERS.pop(eyes.name, None)


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


# -- reacting to what was observed ----------------------------------------


def test_planner_prompt_carries_the_signal_inbox(service):
    """Signals are the loop's reason to act, so they must reach the model --
    an observation nobody reasons about is a log line, not intelligence."""
    service.record_signal(_signal())

    llm = FakeLLM(_decision())
    plan_next_actions(service, llm, limit=2)

    assert WEBHOOK_TITLE in llm.user
    assert service.signal_inbox() in llm.user
    # Observations lead; the business snapshot is only their background.
    assert llm.user.index(WEBHOOK_TITLE) < llm.user.index("Background")
    assert "observ" in llm.system.lower()


def test_signals_shown_to_the_planner_are_marked_processed(service, context_factory):
    """The stop condition for the loop: without this, one blocked milestone
    drives every cycle from now until the heat death of the universe."""
    service.record_signal(_signal())
    llm = FakeLLM(_decision({"action": NOTE_ACTION, "params": {"text": "chased it"}}))

    run_cycle(service, context_factory=context_factory, llm=llm, limit=1, observe=False)

    assert service.list_signals(unprocessed_only=True) == []
    assert service.signal_inbox() == "Nothing new observed."
    # Processed, not resolved -- the condition itself may well still be true.
    assert service.list_signals(open_only=True)[0].title == WEBHOOK_TITLE


def test_an_idle_cycle_still_processes_what_it_read(service, context_factory):
    """Deciding an observation needs no action is a decision, not a skip."""
    service.record_signal(_signal())
    llm = FakeLLM(_decision())

    results = run_cycle(
        service, context_factory=context_factory, llm=llm, limit=1, observe=False
    )

    assert results == []
    assert service.list_signals(unprocessed_only=True) == []


def test_only_the_signals_the_planner_read_are_marked_processed(service, context_factory):
    """`signal_inbox()` ranks and truncates. Marking everything open and
    unprocessed would retire conditions no planner ever saw -- and retire them
    for good, since a repeat observation bumps `times_seen` on the existing
    row without ever clearing `processed_at`."""
    for i in range(25):
        service.record_signal(
            _signal(
                title=f"Condition {i:02d}",
                dedupe_key=f"autonomy-test:bulk:{i}",
                severity="info",
            )
        )
    llm = FakeLLM(_decision())

    run_cycle(service, context_factory=context_factory, llm=llm, limit=1, observe=False)

    still_waiting = service.list_signals(limit=200, open_only=True, unprocessed_only=True)
    assert still_waiting, "the inbox truncates, so some signals must be left over"
    assert all(s.title not in llm.user for s in still_waiting)

    processed = [s for s in service.list_signals(limit=200) if s.processed_at is not None]
    assert processed
    assert all(s.title in llm.user for s in processed)


def test_signals_survive_a_failed_plan_unprocessed(service, context_factory):
    """A planner that never ran never saw them, so they stay in the inbox for
    the next cycle rather than being silently swallowed."""
    service.record_signal(_signal())

    run_cycle(
        service, context_factory=context_factory, llm=BrokenLLM(), limit=1, observe=False
    )

    unprocessed = service.list_signals(unprocessed_only=True)
    assert [s.title for s in unprocessed] == [WEBHOOK_TITLE]


def test_run_cycle_can_skip_observation(service, context_factory, fake_observer):
    """The kernel watches on its own faster clock, so a caller must be able
    to reason without paying for another sweep."""
    llm = FakeLLM(_decision())

    run_cycle(service, context_factory=context_factory, llm=llm, limit=1, observe=False)

    assert fake_observer.calls == 0
    assert service.list_signals() == []


def test_observing_cycle_records_what_it_saw(service, context_factory, fake_observer):
    """Observe -> Reason -> Act in one call: nobody typed this signal in."""
    llm = FakeLLM(_decision())

    before = _event_ids()
    run_cycle(service, context_factory=context_factory, llm=llm, limit=1, observe=True)

    assert fake_observer.calls == 1
    assert WEBHOOK_TITLE in [s.title for s in service.list_signals()]
    assert WEBHOOK_TITLE in llm.user  # observed, then reasoned about
    cycle_events = _new_events(before, "autonomy_cycle")
    assert cycle_events[0].payload["new_signals"] >= 1
    assert cycle_events[0].payload["signals_considered"] >= 1


def test_a_broken_observer_does_not_cost_the_cycle(service, context_factory, monkeypatch):
    """Watching is best-effort; the loop must still think when it fails."""
    def _explode(business):
        raise RuntimeError("the eyes are shut")

    monkeypatch.setattr("aio.observers.cycle.run_observation_cycle", _explode)
    llm = FakeLLM(_decision({"action": NOTE_ACTION, "params": {"text": "still ran"}}))

    results = run_cycle(
        service, context_factory=context_factory, llm=llm, limit=1, observe=True
    )

    assert [r.outcome for r in results] == [ActionOutcome.EXECUTED]


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


def test_watching_is_throttled_separately_from_thinking():
    """Two clocks, because a sweep is a few reads and a plan is a model call.
    Watching on the reasoning interval would mean noticing a dead site up to
    fifteen minutes late for no saving."""
    brain = ExecutiveBrain()
    settings = brain.get_settings()
    assert brain.observe_interval_seconds() == settings.observe_interval_seconds
    assert brain.observe_interval_seconds() < settings.interval_seconds

    assert brain.update_settings(observe_interval_seconds=60).observe_interval_seconds == 60
    assert brain.observe_interval_seconds() == 60


def test_observe_interval_falls_back_when_settings_lack_one():
    """The kernel reads the cadence defensively: settings models travel
    between versions, and one without the field must degrade to watching on
    the reasoning clock rather than crash the loop that owns startup."""

    class _NarrowSettings(BaseModel):
        enabled: bool = False
        interval_seconds: int = 900
        max_actions_per_cycle: int = 2

    brain = ExecutiveBrain()
    brain._settings = _NarrowSettings()  # no public setter for a foreign model
    assert brain.observe_interval_seconds() == 900


def test_kernel_observe_once_watches_without_thinking(service, fake_observer, monkeypatch):
    """The cheap half of the loop: a founder can ask "look now" and it costs
    no model call, so it can be offered freely and often."""
    def _no_model():
        raise AssertionError("observing must not call the model")

    monkeypatch.setattr("aio.llm.build_default_llm", _no_model)

    brain = ExecutiveBrain()
    brain.configure(lambda: service, lambda: ActionContext(business=service, actor="JARVIS"))

    signals = brain.observe_once()

    assert fake_observer.calls == 1
    assert any(s.kind == "test_condition" for s in signals)
    assert brain.observations_run == 1
    assert brain.cycles_run == 0  # watching is not a cycle


def test_overlapping_sweeps_do_not_duplicate_one_condition(tmp_path):
    """The dedupe invariant under the kernel's *own* schedule.

    Watching and thinking run on separate clocks, both dispatch into worker
    threads, and "run now" adds two more entry points -- so overlapping sweeps
    are ordinary, not exotic (300s divides 900s exactly). Recording a signal
    is a find-open-row-else-insert with no unique constraint behind it, so an
    unguarded overlap writes the same standing condition twice and it is
    reported to the founder as two separate problems forever.

    A file-backed database on purpose: `sqlite:///:memory:` gives each thread
    its own database, which would make this pass without proving anything.
    """
    from aio.observers.base import _REGISTRY as _OBSERVERS, Observer, register_observer

    url = f"sqlite:///{(tmp_path / 'kernel.db').as_posix()}"
    BusinessService(database_url=url).init_schema()

    class _SlowEyes(Observer):
        name = "autonomy_test_slow_eyes"
        display_name = "Slow Eyes"
        watches = ("test_condition",)

        def observe(self, business) -> list[Signal]:
            # Widens a window every real observer already has -- the website
            # observer sits in an HTTP call at exactly this point.
            time.sleep(0.2)
            return [_signal(source=self.name, dedupe_key="autonomy-test:slow")]

    register_observer(_SlowEyes())
    failures: list[BaseException] = []

    def _sweep() -> None:
        try:
            brain.observe_once()
        except BaseException as exc:  # noqa: BLE001 -- reported, not swallowed
            failures.append(exc)

    try:
        brain = ExecutiveBrain()
        brain.configure(
            lambda: BusinessService(database_url=url),
            lambda: ActionContext(business=BusinessService(database_url=url), actor="JARVIS"),
        )
        threads = [threading.Thread(target=_sweep) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
    finally:
        _OBSERVERS.pop(_SlowEyes.name, None)

    assert failures == []
    rows = [
        s
        for s in BusinessService(database_url=url).list_signals(limit=200)
        if s.dedupe_key == "autonomy-test:slow"
    ]
    assert len(rows) == 1
    assert rows[0].times_seen == 2
    assert brain.observations_run == 2


def test_unconfigured_kernel_observes_nothing_without_crashing():
    assert ExecutiveBrain().observe_once() == []


def test_kernel_run_once_ignores_the_enabled_switch(service, context_factory, monkeypatch):
    """`enabled` gates JARVIS acting unprompted. The founder pressing 'run
    now' is a direct instruction and must work with autonomy switched off."""
    llm = FakeLLM(_decision({"action": NOTE_ACTION, "params": {"text": "on demand"}}))
    monkeypatch.setattr("aio.llm.build_default_llm", lambda: llm)

    brain = ExecutiveBrain()
    brain.configure(lambda: service, context_factory)
    assert brain.get_settings().enabled is False

    assert len(brain.run_once()) == 1
