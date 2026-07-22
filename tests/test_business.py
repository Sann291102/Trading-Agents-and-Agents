"""Executive Business OS tests -- BusinessService storage + seed, the
business agent roster's presence in the shared agent registry, and the
voice-first assistant behaviors (greeting, conversation history) in demo
mode."""

import pytest

from aio.agents import BUSINESS_AGENT_CLASSES, all_agent_classes
from aio.agents.business import ChiefOfStaffAgent, ExecutiveAssistantAgent
from aio.business import BusinessService
from aio.llm import DemoAnthropicClient
from aio.models.business import (
    Approval,
    BusinessMetricSnapshot,
    Company,
    ConversationTurn,
    Milestone,
    next_stage,
)
from aio.models.signals import Signal


@pytest.fixture()
def service() -> BusinessService:
    svc = BusinessService(database_url="sqlite:///:memory:")
    svc.init_schema()
    return svc


def test_tradew_is_seeded_as_pre_launch(service: BusinessService):
    """TradeW has not launched. Seeding it as 'operating' would make every
    briefing talk about customers and revenue that do not exist."""
    companies = service.list_companies()
    assert [c.name for c in companies] == ["TradeW"]
    assert companies[0].industry.startswith("Fintech")
    assert companies[0].stage == "building"
    assert companies[0].is_pre_revenue


def test_stage_ladder():
    assert next_stage("idea") == "building"
    assert next_stage("building") == "launched"
    assert next_stage("scaling") is None
    assert next_stage("nonsense") is None


def test_milestone_lifecycle(service: BusinessService):
    company = service.list_companies()[0]
    created = service.create_milestone(
        Milestone(company_id=company.id, title="Ship private beta", owner_agent="Operations Director")
    )
    assert created.status == "todo"

    blocked = service.set_milestone_status(created.id, "blocked", blocker="Waiting on broker API")
    assert blocked is not None
    assert blocked.status == "blocked"
    assert blocked.blocker == "Waiting on broker API"

    done = service.set_milestone_status(created.id, "done")
    assert done is not None
    assert done.completed_at is not None
    # Moving off 'blocked' must clear the stale reason.
    assert done.blocker == ""


def test_milestone_status_is_validated(service: BusinessService):
    company = service.list_companies()[0]
    milestone = service.create_milestone(Milestone(company_id=company.id, title="X"))
    with pytest.raises(ValueError):
        service.set_milestone_status(milestone.id, "almost")


def test_replan_preserves_banked_work(service: BusinessService):
    """Regenerating a launch plan must not erase milestones the founder has
    already finished or started."""
    company = service.list_companies()[0]
    finished = service.create_milestone(Milestone(company_id=company.id, title="Pick the core workflow"))
    service.set_milestone_status(finished.id, "done")
    stale = service.create_milestone(Milestone(company_id=company.id, title="Old idea to drop"))
    assert stale.status == "todo"

    after = service.replace_milestones(
        company.id,
        [
            Milestone(company_id=company.id, title="Pick the core workflow"),
            Milestone(company_id=company.id, title="Recruit design partners"),
        ],
    )
    titles = [m.title for m in after]
    assert "Pick the core workflow" in titles
    assert "Recruit design partners" in titles
    assert "Old idea to drop" not in titles
    # The completed one survived as completed, and wasn't duplicated.
    assert titles.count("Pick the core workflow") == 1
    assert next(m for m in after if m.title == "Pick the core workflow").status == "done"


def test_pre_revenue_snapshot_states_there_are_no_numbers(service: BusinessService):
    """The whole point of the stage split: a pre-launch company's context
    must say plainly that revenue does not exist, so the model cannot fill
    the silence with plausible-looking figures."""
    company = service.list_companies()[0]
    service.create_milestone(
        Milestone(company_id=company.id, title="Ship private beta", owner_agent="Operations Director")
    )
    context = service.snapshot_for_briefing()
    assert "PRE-REVENUE" in context
    assert "no customers, no revenue, no MRR" in context.lower() or "No customers, no revenue" in context
    assert "Ship private beta" in context
    assert "Operations Director" in context
    # No metrics vocabulary should appear for a company with no metrics.
    assert "MRR $" not in context


def test_launched_company_still_reports_metrics(service: BusinessService):
    """The stage split must not break the metrics path for a real business."""
    company = service.create_company(Company(name="Acme", stage="operating"))
    service.record_metrics(
        BusinessMetricSnapshot(company_id=company.id, mrr=5000, customers=42)
    )
    context = service.snapshot_for_briefing()
    assert "MRR $5,000" in context
    assert "42 customers" in context


def test_seed_is_idempotent(service: BusinessService):
    service.init_schema()
    service.init_schema()
    assert len(service.list_companies()) == 1


def test_create_and_get_company(service: BusinessService):
    created = service.create_company(Company(name="Acme", stage="building"))
    fetched = service.get_company(created.id)
    assert fetched is not None
    assert fetched.name == "Acme"
    assert fetched.stage == "building"


def test_metrics_round_trip_newest_first(service: BusinessService):
    company = service.list_companies()[0]
    service.record_metrics(BusinessMetricSnapshot(company_id=company.id, mrr=1000, customers=10))
    service.record_metrics(BusinessMetricSnapshot(company_id=company.id, mrr=1500, customers=14))
    history = service.list_metrics(company.id)
    assert len(history) == 2
    assert history[0].mrr == 1500  # newest first
    latest = service.latest_metrics(company.id)
    assert latest is not None and latest.customers == 14


def test_approval_lifecycle(service: BusinessService):
    approval = service.create_approval(Approval(title="Approve Q3 marketing budget"))
    assert approval.status == "pending"
    assert [a.id for a in service.list_approvals(status="pending")] == [approval.id]

    decided = service.decide_approval(approval.id, "approved")
    assert decided is not None
    assert decided.status == "approved"
    assert decided.decided_at is not None
    assert service.list_approvals(status="pending") == []


def test_decide_approval_rejects_bad_decision(service: BusinessService):
    approval = service.create_approval(Approval(title="X"))
    with pytest.raises(ValueError):
        service.decide_approval(approval.id, "maybe")


def test_decide_unknown_approval_returns_none(service: BusinessService):
    assert service.decide_approval("nope", "approved") is None


def _signal(**overrides) -> Signal:
    base = {
        "source": "business_state",
        "kind": "milestone_blocked",
        "title": "Broker API is blocking launch",
        "dedupe_key": "milestone_blocked:abc",
        "severity": "notable",
    }
    return Signal(**{**base, **overrides})


def test_repeated_observation_collapses_onto_one_signal(service: BusinessService):
    """The core invariant of the observer system. Observers are stateless and
    re-report standing conditions every cycle, so without dedupe the feed
    would fill with copies of the same fact and drown the real news."""
    first = service.record_signal(_signal())
    second = service.record_signal(_signal())
    third = service.record_signal(_signal())

    assert first.id == second.id == third.id
    assert third.times_seen == 3
    assert len(service.list_signals(open_only=True)) == 1


def test_repeat_observation_refreshes_the_wording(service: BusinessService):
    """A standing condition can worsen between observations -- the row must
    carry the current truth, not the first thing ever seen."""
    service.record_signal(_signal(title="3 tickets open", severity="info"))
    latest = service.record_signal(_signal(title="30 tickets open", severity="urgent"))
    assert latest.title == "30 tickets open"
    assert latest.severity == "urgent"
    assert latest.times_seen == 2


def test_distinct_conditions_stay_distinct(service: BusinessService):
    service.record_signal(_signal())
    service.record_signal(_signal(kind="website_offline", dedupe_key="website_offline:tradew"))
    assert len(service.list_signals(open_only=True)) == 2


def test_conditions_an_observer_stops_reporting_are_resolved(service: BusinessService):
    """Otherwise a fixed problem stays true forever: the site comes back up
    but 'website offline' keeps driving the executive loop."""
    service.record_signal(_signal())
    service.record_signal(_signal(kind="website_offline", dedupe_key="website_offline:tradew"))

    resolved = service.resolve_signals_absent_from("business_state", {"website_offline:tradew"})
    assert resolved == 1

    still_open = {s.dedupe_key for s in service.list_signals(open_only=True)}
    assert still_open == {"website_offline:tradew"}


def test_resolving_ignores_other_sources(service: BusinessService):
    """One observer's report is the truth only for its own source -- it must
    never close another observer's signals."""
    service.record_signal(_signal(source="website", dedupe_key="website_offline:tradew"))
    resolved = service.resolve_signals_absent_from("business_state", set())
    assert resolved == 0
    assert len(service.list_signals(open_only=True)) == 1


def test_signal_inbox_puts_urgent_and_repeated_first(service: BusinessService):
    """A condition seen many times has been ignored many times, so repetition
    is a priority signal in its own right."""
    service.record_signal(_signal(dedupe_key="a", title="Low priority", severity="info"))
    for _ in range(4):
        service.record_signal(_signal(dedupe_key="b", title="Seen often", severity="info"))
    service.record_signal(_signal(dedupe_key="c", title="On fire", severity="urgent"))

    inbox = service.signal_inbox()
    assert inbox.index("On fire") < inbox.index("Seen often") < inbox.index("Low priority")
    assert "seen 4x" in inbox


def test_processing_empties_the_inbox_without_resolving(service: BusinessService):
    """Processed means 'the loop took it into account', not 'it stopped being
    true' -- the condition stays open until an observer says otherwise."""
    service.record_signal(_signal())
    open_ids = [s.id for s in service.list_signals(open_only=True, unprocessed_only=True)]
    assert service.mark_signals_processed(open_ids) == 1
    assert service.signal_inbox() == "Nothing new observed."
    assert len(service.list_signals(open_only=True)) == 1


def test_marking_processed_is_idempotent(service: BusinessService):
    stored = service.record_signal(_signal())
    assert service.mark_signals_processed([stored.id]) == 1
    assert service.mark_signals_processed([stored.id]) == 0
    assert service.mark_signals_processed([]) == 0


def test_conversation_turns_round_trip_oldest_first(service: BusinessService):
    service.save_turn(ConversationTurn(who="jarvis", text="Welcome back."))
    service.save_turn(ConversationTurn(who="founder", text="How is TradeW?"))
    service.save_turn(ConversationTurn(who="jarvis", text="MRR is steady."))
    turns = service.recent_turns()
    assert [(t.who, t.text) for t in turns] == [
        ("jarvis", "Welcome back."),
        ("founder", "How is TradeW?"),
        ("jarvis", "MRR is steady."),
    ]


def test_recent_turns_limit_keeps_the_newest(service: BusinessService):
    for i in range(5):
        service.save_turn(ConversationTurn(who="founder", text=f"turn {i}"))
    turns = service.recent_turns(limit=2)
    assert [t.text for t in turns] == ["turn 3", "turn 4"]


def test_briefing_snapshot_contains_real_numbers(service: BusinessService):
    """Metrics reach the briefing context for a company far enough along to
    have them. (Seeded TradeW is pre-launch, so it is deliberately not the
    subject here -- see test_pre_revenue_snapshot_states_there_are_no_numbers.)"""
    company = service.create_company(Company(name="Northwind", stage="operating"))
    service.record_metrics(
        BusinessMetricSnapshot(company_id=company.id, mrr=12000, customers=340, cash_balance=250000)
    )
    service.create_approval(Approval(title="Sign the new support vendor"))
    context = service.snapshot_for_briefing()
    assert "Northwind" in context
    assert "$12,000" in context
    assert "340 customers" in context
    assert "Sign the new support vendor" in context


def test_roster_names_are_offered_to_the_planner():
    """Milestone owners have to be real agents or the work can never be
    delegated -- a live run invented 'Product Agent' and 'Engineering Agent'
    before the roster was passed into the prompt."""
    from aio.agents.business import business_roster_names

    names = business_roster_names()
    roles = {cls.role for cls in BUSINESS_AGENT_CLASSES}
    for role in roles:
        assert role in names
    assert "Product Agent" not in names
    assert "Engineering Agent" not in names


def test_demo_launch_plan_owners_are_real_agents():
    """The demo plan must obey the same rule it teaches."""
    from aio.agents.business import ChiefOfStaffAgent

    plan = ChiefOfStaffAgent(DemoAnthropicClient()).launch_plan(
        "TradeW", "launched", "Company: TradeW (building) -- PRE-REVENUE"
    )
    roles = {cls.role for cls in BUSINESS_AGENT_CLASSES}
    assert plan.milestones
    for milestone in plan.milestones:
        assert milestone.owner_agent in roles, f"{milestone.owner_agent!r} is not a real agent"


def test_business_agents_registered():
    roles = {cls.role for cls in all_agent_classes()}
    assert "Chief of Staff" in roles
    assert "Executive Assistant" in roles
    assert "Marketing Director" in roles
    assert "Finance Manager" in roles
    assert len(BUSINESS_AGENT_CLASSES) == 14


def test_chief_of_staff_and_assistant_have_business_departments():
    assert ChiefOfStaffAgent.department == "Executive Office"
    assert ExecutiveAssistantAgent.department == "Executive Office"


def test_assistant_converse_accepts_history_in_demo_mode():
    ea = ExecutiveAssistantAgent(DemoAnthropicClient())
    reply = ea.converse(
        "And what should I do about it?",
        "Company: TradeW -- MRR $12,000",
        history=[
            ConversationTurn(who="founder", text="How is TradeW doing?"),
            ConversationTurn(who="jarvis", text="MRR is at twelve thousand."),
        ],
    )
    assert reply.reply
    assert isinstance(reply.suggested_actions, list)


def test_assistant_turns_an_order_into_an_action():
    """JARVIS is an operator, not a chatbot: telling it to do something must
    produce a real action to run, not advice about doing it."""
    ea = ExecutiveAssistantAgent(DemoAnthropicClient())
    catalog = "- delegate_to_agent (safe): Give a task to a business agent [params: agent_role, task]"
    intent = ea.act(
        "Have the Operations Director scope the MVP",
        "Company: TradeW (building) -- PRE-REVENUE: not launched yet.",
        catalog,
    )
    assert intent.action == "delegate_to_agent"
    assert intent.params.get("agent_role") == "Operations Director"
    assert intent.params.get("task")
    # The task must be the founder's instruction, not the whole prompt.
    assert "Business context:" not in intent.params["task"]
    assert intent.reply


def test_assistant_answers_a_question_without_acting():
    """A question is not an order -- answering must not trigger work."""
    ea = ExecutiveAssistantAgent(DemoAnthropicClient())
    intent = ea.act(
        "How are we doing?",
        "Company: TradeW (building) -- PRE-REVENUE: not launched yet.",
        "- delegate_to_agent (safe): Give a task to a business agent [params: agent_role, task]",
    )
    assert intent.action == ""
    assert intent.reply


def test_assistant_greeting_in_demo_mode():
    ea = ExecutiveAssistantAgent(DemoAnthropicClient())
    greeting = ea.greet("Company: TradeW -- no snapshots yet")
    assert greeting.reply
    assert greeting.suggested_actions


def test_chief_of_staff_briefing_in_demo_mode():
    chief = ChiefOfStaffAgent(DemoAnthropicClient())
    briefing = chief.briefing("Company: TradeW -- MRR $12,000, 340 customers")
    assert briefing.headline
    assert briefing.business_health in ("strong", "stable", "warning", "critical")
    assert briefing.priorities


def test_demo_client_covers_every_business_role():
    """Every business agent must produce output in demo mode -- the
    zero-cost provider is the default local-run path."""
    for cls in BUSINESS_AGENT_CLASSES:
        text = cls(DemoAnthropicClient()).execute("Summarize current state")
        assert text, f"{cls.role} produced no demo output"
