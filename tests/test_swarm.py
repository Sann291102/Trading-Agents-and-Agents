"""Engineering-swarm stage: ruflo agent loading, planning, execution,
validation -- exercised end-to-end on the demo LLM client (no network)."""

from aio.agents import RUFLO_AGENT_CLASSES, all_agent_classes, ruflo_role_names
from aio.agents.parsing import extract_role_from_system_prompt
from aio.llm.demo_client import DemoAnthropicClient
from aio.orchestration.graph import run_legacy_organization


def test_ruflo_agents_are_registered():
    assert len(RUFLO_AGENT_CLASSES) == 30
    registered_roles = {cls.role for cls in all_agent_classes()}
    assert ruflo_role_names() <= registered_roles
    # 8 hand-written agents + 30 imported specialists. ">=" not "==":
    # other tests define throwaway Agent subclasses that stay in
    # Agent.__subclasses__() for the life of the process.
    assert len(all_agent_classes()) >= 38


def test_ruflo_prompts_declare_their_own_role():
    """The demo client and status tracking route on the 'You are the
    <role>' prefix -- every generated prompt must round-trip through it."""
    for role, cls in RUFLO_AGENT_CLASSES.items():
        assert extract_role_from_system_prompt(cls.system_prompt) == role


def test_run_organization_runs_swarm_after_approval():
    result = run_legacy_organization(
        goal="Build a paper-trading platform for the Indian stock market",
        llm=DemoAnthropicClient(),
        persist=False,
    )

    assert result["approved"] is True

    plan = result["swarm_plan"]
    assert len(plan.assignments) == 6
    assert {a.role for a in plan.assignments} <= ruflo_role_names()

    results = result["swarm_results"]
    assert len(results) == len(plan.assignments)
    assert all(r.error is None for r in results)
    assert all(r.output for r in results)

    validation = result["swarm_validation"]
    assert validation.passed is True


def test_swarm_can_be_disabled():
    result = run_legacy_organization(
        goal="Build a paper-trading platform for the Indian stock market",
        llm=DemoAnthropicClient(),
        persist=False,
        swarm=False,
    )
    assert result["approved"] is True
    assert "swarm_plan" not in result
