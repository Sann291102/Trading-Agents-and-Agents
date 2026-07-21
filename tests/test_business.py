"""Executive Business OS tests -- BusinessService storage + seed, the
business agent roster's presence in the shared agent registry, and the
voice-first assistant behaviors (greeting, conversation history) in demo
mode."""

import pytest

from aio.agents import BUSINESS_AGENT_CLASSES, all_agent_classes
from aio.agents.business import ChiefOfStaffAgent, ExecutiveAssistantAgent
from aio.business import BusinessService
from aio.llm import DemoAnthropicClient
from aio.models.business import Approval, BusinessMetricSnapshot, Company, ConversationTurn


@pytest.fixture()
def service() -> BusinessService:
    svc = BusinessService(database_url="sqlite:///:memory:")
    svc.init_schema()
    return svc


def test_tradew_is_seeded(service: BusinessService):
    companies = service.list_companies()
    assert [c.name for c in companies] == ["TradeW"]
    assert companies[0].industry.startswith("Fintech")


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
    company = service.list_companies()[0]
    service.record_metrics(
        BusinessMetricSnapshot(company_id=company.id, mrr=12000, customers=340, cash_balance=250000)
    )
    service.create_approval(Approval(title="Sign the new support vendor"))
    context = service.snapshot_for_briefing()
    assert "TradeW" in context
    assert "$12,000" in context
    assert "340 customers" in context
    assert "Sign the new support vendor" in context


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
