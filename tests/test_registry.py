from aio.agents import Agent
from aio.agents.registry import AgentStatusTracker, all_agent_classes
from aio.events.bus import EventBus, OrgEvent


def test_all_agent_classes_includes_every_implemented_agent():
    roles = {cls.role for cls in all_agent_classes()}

    # The 8 hand-written agents...
    assert {
        "JARVIS",
        "Research Coordinator",
        "Domain Expert",
        "Market Research Analyst",
        "Competitor Intelligence Agent",
        "Technical Research Agent",
        "Product Manager",
        "Backend Lead",
    } <= roles
    # ...plus the 30 ruflo-imported swarm specialists (see
    # agents/ruflo_defs/manifest.json and tests/test_swarm.py).
    from aio.agents import ruflo_role_names

    assert ruflo_role_names() <= roles
    # The base class itself must not appear -- it never overrides `role`.
    assert Agent.role not in roles


def test_all_agent_classes_reports_correct_departments():
    departments = {cls.role: cls.department for cls in all_agent_classes()}

    assert departments["JARVIS"] == "Executive"
    assert departments["Research Coordinator"] == "Research"
    assert departments["Domain Expert"] == "Research"
    assert departments["Market Research Analyst"] == "Research"
    assert departments["Competitor Intelligence Agent"] == "Research"
    assert departments["Technical Research Agent"] == "Research"
    assert departments["Product Manager"] == "Product"
    assert departments["Backend Lead"] == "Engineering"


def test_new_agent_subclass_appears_without_further_registration():
    class FutureDesignAgent(Agent):
        role = "UI Designer"
        department = "Design"

    roles = {cls.role for cls in all_agent_classes()}
    assert "UI Designer" in roles


def _make_tracker() -> tuple[AgentStatusTracker, EventBus]:
    bus = EventBus()
    tracker = AgentStatusTracker.__new__(AgentStatusTracker)
    tracker._lock = __import__("threading").Lock()
    tracker._statuses = {}
    bus.add_listener(tracker._on_event)
    return tracker, bus


def test_status_tracker_starts_executing_on_agent_started():
    tracker, bus = _make_tracker()

    bus.publish(
        OrgEvent(
            type="agent_started",
            agent_role="Domain Expert",
            department="Research",
            message="Domain Expert started",
        )
    )

    snapshot = {s.role: s for s in tracker.snapshot()}
    assert snapshot["Domain Expert"].status == "executing"


def test_status_tracker_moves_to_completed_on_clean_finish():
    tracker, bus = _make_tracker()
    bus.publish(OrgEvent(type="agent_started", agent_role="Domain Expert", message="started"))
    bus.publish(
        OrgEvent(
            type="agent_finished",
            agent_role="Domain Expert",
            department="Research",
            confidence=0.82,
            duration_seconds=1.5,
            message="Domain Expert completed",
            payload={"handoff_target": "Research Coordinator", "error": None},
        )
    )

    status = {s.role: s for s in tracker.snapshot()}["Domain Expert"]
    assert status.status == "completed"
    assert status.last_confidence == 0.82
    assert status.last_duration_seconds == 1.5


def test_status_tracker_moves_to_needs_review_on_error():
    tracker, bus = _make_tracker()
    bus.publish(OrgEvent(type="agent_started", agent_role="Backend Lead", message="started"))
    bus.publish(
        OrgEvent(
            type="agent_finished",
            agent_role="Backend Lead",
            department="Engineering",
            message="Backend Lead failed: boom",
            payload={"handoff_target": None, "error": "boom"},
        )
    )

    status = {s.role: s for s in tracker.snapshot()}["Backend Lead"]
    assert status.status == "needs_review"


def test_status_tracker_ignores_unrelated_event_types():
    tracker, bus = _make_tracker()

    bus.publish(OrgEvent(type="research_complete", department="Research", message="done"))

    assert tracker.snapshot() == []
