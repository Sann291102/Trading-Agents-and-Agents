"""Action catalog tests -- the capabilities JARVIS executes.

Everything runs against an in-memory BusinessService and (where an agent is
involved) the demo LLM, so the whole engine is exercised for real: the
registry, parameter validation, the audit trail, and the defensive paths
that must come back as a FAILED result the founder can act on rather than
an exception that kills the autonomous loop.
"""

import pytest

from aio.actions import (
    ActionContext,
    ActionOutcome,
    ActionRisk,
    UnknownAction,
    all_actions,
    execute_action,
    get_action,
)
from aio.business import BusinessService
from aio.llm import DemoAnthropicClient
from aio.memory.semantic import SemanticMemory
from aio.memory.service import MemoryService
from aio.models.business import BusinessMetricSnapshot

EXPECTED_ACTIONS = {
    "add_milestone",
    "delegate_to_agent",
    "raise_approval",
    "record_company_metrics",
    "request_agent_report",
    "save_memory_entry",
    "search_memory",
    "set_milestone_status",
    "update_company_stage",
}


@pytest.fixture()
def business() -> BusinessService:
    svc = BusinessService(database_url="sqlite:///:memory:")
    svc.init_schema()
    return svc


@pytest.fixture()
def context(business: BusinessService) -> ActionContext:
    return ActionContext(business=business, actor="JARVIS")


@pytest.fixture()
def memory() -> MemoryService:
    svc = MemoryService(database_url="sqlite:///:memory:")
    svc.init_schema()
    return svc


@pytest.fixture()
def demo_llm(monkeypatch):
    """Delegation builds its own client from settings; pin it to the demo
    provider so these tests never depend on a key or the network."""
    monkeypatch.setattr(
        "aio.actions.catalog.delegation.build_default_llm",
        lambda: DemoAnthropicClient(),
    )


# -- the registry ------------------------------------------------------------


def test_registry_is_populated():
    """Importing aio.actions must be enough -- actions register by import
    side effect, so a missing catalog import means JARVIS silently can do
    nothing at all."""
    names = {spec.name for spec in all_actions()}
    assert EXPECTED_ACTIONS <= names


def test_every_action_exposes_a_parameter_schema():
    """The planner fills parameters from the schema; an action without
    described fields cannot be called correctly by a model."""
    for spec in all_actions():
        described = spec.describe()
        assert described["risk"] in {risk.value for risk in ActionRisk}
        assert "properties" in described["params_schema"]


def test_unknown_action_raises(context: ActionContext):
    with pytest.raises(UnknownAction):
        execute_action("teleport_the_founder", {}, context)


# -- business ops ------------------------------------------------------------


def test_safe_action_executes_and_is_recorded(context: ActionContext):
    """A SAFE action runs immediately (no approval) and leaves an audit
    trail -- the activity feed is built entirely from these runs."""
    result = execute_action(
        "record_company_metrics",
        {"company_name": "TradeW", "mrr": 1200, "customers": 8},
        context,
    )
    assert result.outcome is ActionOutcome.EXECUTED
    assert result.ok

    runs = context.business.list_action_runs()
    assert runs[0].action == "record_company_metrics"
    assert runs[0].outcome == "executed"
    assert runs[0].actor == "JARVIS"
    assert runs[0].summary


def test_recorded_metrics_reach_the_company(context: ActionContext):
    execute_action(
        "record_company_metrics",
        {"company_name": "tradew", "mrr": 1200, "customers": 8, "notes": "first paying users"},
        context,
    )
    company = context.business.list_companies()[0]
    history = context.business.list_metrics(company.id)
    assert len(history) == 1
    assert history[0].mrr == 1200
    assert history[0].customers == 8
    assert history[0].notes == "first paying users"


def test_record_company_metrics_rejects_unknown_company(context: ActionContext):
    """User-input problems must come back as a FAILED result naming the
    valid options, never as an exception."""
    result = execute_action(
        "record_company_metrics",
        {"company_name": "Umbrella Corp", "mrr": 999},
        context,
    )
    assert result.outcome is ActionOutcome.FAILED
    assert "Umbrella Corp" in result.summary
    assert "TradeW" in result.detail
    assert context.business.list_action_runs()[0].outcome == "failed"


def test_record_company_metrics_needs_at_least_one_number(context: ActionContext):
    result = execute_action("record_company_metrics", {"company_name": "TradeW"}, context)
    assert result.outcome is ActionOutcome.FAILED


def test_unstated_metrics_carry_forward(context: ActionContext):
    """Stating one figure must not zero out the rest of the business."""
    company = context.business.list_companies()[0]
    context.business.record_metrics(
        BusinessMetricSnapshot(company_id=company.id, mrr=1000, customers=10, cash_balance=250000)
    )
    execute_action("record_company_metrics", {"company_name": "TradeW", "customers": 14}, context)

    latest = context.business.latest_metrics(company.id)
    assert latest is not None
    assert latest.customers == 14
    assert latest.cash_balance == 250000
    assert latest.mrr == 1000


def test_add_milestone_rejects_an_invented_owner(context: ActionContext):
    """A milestone owned by an agent that does not exist can never be
    delegated to anyone."""
    result = execute_action(
        "add_milestone",
        {"company_name": "TradeW", "title": "Ship beta", "owner_agent": "Product Agent"},
        context,
    )
    assert result.outcome is ActionOutcome.FAILED
    assert "Product Agent" in result.summary
    assert "Operations Director" in result.detail


def test_milestone_can_be_added_then_moved(context: ActionContext):
    added = execute_action(
        "add_milestone",
        {
            "company_name": "TradeW",
            "title": "Ship the private beta",
            "detail": "One workflow, real users.",
            "owner_agent": "operations director",
        },
        context,
    )
    assert added.ok
    company = context.business.list_companies()[0]
    milestone = context.business.list_milestones(company.id)[0]
    # The roster's canonical spelling wins over whatever casing was given.
    assert milestone.owner_agent == "Operations Director"

    # Titles arrive from speech or a paraphrasing model, so matching is fuzzy.
    moved = execute_action(
        "set_milestone_status",
        {
            "company_name": "TradeW",
            "milestone_title": "private beta",
            "status": "blocked",
            "blocker": "Waiting on broker API keys",
        },
        context,
    )
    assert moved.ok
    updated = context.business.list_milestones(company.id)[0]
    assert updated.status == "blocked"
    assert updated.blocker == "Waiting on broker API keys"


def test_set_milestone_status_rejects_a_bad_status(context: ActionContext):
    execute_action(
        "add_milestone",
        {"company_name": "TradeW", "title": "Ship the private beta"},
        context,
    )
    result = execute_action(
        "set_milestone_status",
        {"company_name": "TradeW", "milestone_title": "Ship the private beta", "status": "almost"},
        context,
    )
    assert result.outcome is ActionOutcome.FAILED
    assert "in_progress" in result.detail


def test_set_milestone_status_reports_unknown_milestone(context: ActionContext):
    execute_action("add_milestone", {"company_name": "TradeW", "title": "Ship beta"}, context)
    result = execute_action(
        "set_milestone_status",
        {"company_name": "TradeW", "milestone_title": "buy a yacht", "status": "done"},
        context,
    )
    assert result.outcome is ActionOutcome.FAILED
    assert "Ship beta" in result.detail


def test_update_company_stage_moves_the_company(context: ActionContext):
    result = execute_action(
        "update_company_stage", {"company_name": "TradeW", "stage": "launched"}, context
    )
    assert result.ok
    company = context.business.list_companies()[0]
    assert company.stage == "launched"
    assert not company.is_pre_revenue


def test_update_company_stage_validates_the_stage(context: ActionContext):
    result = execute_action(
        "update_company_stage", {"company_name": "TradeW", "stage": "unicorn"}, context
    )
    assert result.outcome is ActionOutcome.FAILED
    assert "building" in result.detail
    assert context.business.list_companies()[0].stage == "building"


def test_raise_approval_parks_a_question_not_a_pending_action(context: ActionContext):
    """raise_approval is JARVIS *asking*; approving it records an answer
    rather than executing work, so it must carry no pending action."""
    result = execute_action(
        "raise_approval",
        {
            "company_name": "TradeW",
            "title": "Do we price the beta at zero?",
            "detail": "Free gets users faster; paid validates willingness to pay.",
        },
        context,
    )
    assert result.ok
    pending = context.business.list_approvals(status="pending")
    assert len(pending) == 1
    assert pending[0].title == "Do we price the beta at zero?"
    assert pending[0].requested_by == "JARVIS"
    assert not pending[0].is_executable


# -- delegation --------------------------------------------------------------


def test_delegate_to_agent_rejects_an_invented_role(context: ActionContext):
    """Validated before any model is built, so an invented role costs
    nothing and comes back with the real roster."""
    result = execute_action(
        "delegate_to_agent",
        {"agent_role": "Product Agent", "task": "Scope the MVP"},
        context,
    )
    assert result.outcome is ActionOutcome.FAILED
    assert "Product Agent" in result.summary
    assert "Operations Director" in result.detail
    assert "Chief of Staff" in result.detail


def test_delegate_to_agent_returns_the_agents_real_output(context: ActionContext, demo_llm):
    result = execute_action(
        "delegate_to_agent",
        {
            "agent_role": "Operations Director",
            "task": "Scope the smallest shippable version of TradeW",
            "company_name": "TradeW",
        },
        context,
    )
    assert result.outcome is ActionOutcome.EXECUTED
    assert result.detail, "the agent's actual work must come back on the result"
    assert result.data["agent_role"] == "Operations Director"
    assert result.data["output"] == result.detail
    assert "Operations Director" in result.summary
    # The run is recorded with the agent's output, so the feed shows the work.
    assert context.business.list_action_runs()[0].detail == result.detail


def test_delegation_files_the_output_to_memory(
    business: BusinessService, memory: MemoryService, demo_llm
):
    context = ActionContext(business=business, actor="JARVIS", memory=memory)
    result = execute_action(
        "delegate_to_agent",
        {"agent_role": "Finance Manager", "task": "Sanity-check the launch pricing"},
        context,
    )
    assert result.ok
    assert result.data["filed_to_memory"] is True
    entries = memory.list_entries()
    assert len(entries) == 1
    assert entries[0].owner == "Finance Manager"
    assert entries[0].summary == result.detail


def test_delegation_survives_having_no_memory(context: ActionContext, demo_llm):
    """Memory is optional plumbing -- the work was still done."""
    result = execute_action(
        "delegate_to_agent",
        {"agent_role": "Sales Director", "task": "List ten design partners to approach"},
        context,
    )
    assert result.ok
    assert result.data["filed_to_memory"] is False


def test_request_agent_report_grounds_and_returns(context: ActionContext, demo_llm):
    result = execute_action(
        "request_agent_report",
        {"agent_role": "Business Analyst", "topic": "progress toward launch"},
        context,
    )
    assert result.ok
    assert result.data["agent_role"] == "Business Analyst"
    assert result.detail


def test_request_agent_report_rejects_an_invented_role(context: ActionContext):
    result = execute_action(
        "request_agent_report",
        {"agent_role": "Chief Vibes Officer", "topic": "morale"},
        context,
    )
    assert result.outcome is ActionOutcome.FAILED


# -- knowledge ---------------------------------------------------------------


def test_save_memory_entry_persists_and_is_typed(business: BusinessService, memory: MemoryService):
    context = ActionContext(business=business, actor="Knowledge Manager", memory=memory)
    result = execute_action(
        "save_memory_entry",
        {
            "title": "Broker API sandbox needs a signed agreement",
            "summary": "Sandbox access took three weeks; start it before the next integration.",
            "entry_type": "lesson_learned",
            "tags": ["broker", "integration"],
        },
        context,
    )
    assert result.ok
    entries = memory.list_entries()
    assert len(entries) == 1
    assert entries[0].type.value == "lesson_learned"
    assert entries[0].owner == "Knowledge Manager"
    assert "broker" in entries[0].metadata.tags


def test_save_memory_entry_rejects_an_invented_type(
    business: BusinessService, memory: MemoryService
):
    context = ActionContext(business=business, memory=memory)
    result = execute_action(
        "save_memory_entry",
        {"title": "X", "summary": "Y", "entry_type": "vibe"},
        context,
    )
    assert result.outcome is ActionOutcome.FAILED
    assert "lesson_learned" in result.detail
    assert memory.list_entries() == []


def test_save_memory_entry_without_memory_fails_clearly(context: ActionContext):
    result = execute_action("save_memory_entry", {"title": "X", "summary": "Y"}, context)
    assert result.outcome is ActionOutcome.FAILED
    assert "memory" in result.summary.lower()


def test_search_memory_returns_past_work(business: BusinessService):
    semantic = SemanticMemory(database_url="sqlite://")
    semantic.init_collection()
    semantic.upsert_project("p1", "Launch a trading platform", "Shipped the private beta")
    context = ActionContext(business=business, semantic=semantic)

    result = execute_action("search_memory", {"query": "trading platform launch"}, context)
    assert result.ok
    assert result.data["matches"]
    assert "trading platform" in result.detail.lower()


def test_search_memory_without_semantic_fails_clearly(context: ActionContext):
    result = execute_action("search_memory", {"query": "anything"}, context)
    assert result.outcome is ActionOutcome.FAILED
    assert "memory" in result.summary.lower()


def test_knowledge_actions_declare_the_memory_connector():
    for name in ("save_memory_entry", "search_memory"):
        spec = get_action(name)
        assert spec is not None
        assert spec.connector == "memory"
