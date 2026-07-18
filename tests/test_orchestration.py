import json

from aio.agents.parsing import extract_role_from_system_prompt
from aio.memory.long_term import LongTermMemory
from aio.memory.semantic import SemanticMemory
from aio.memory.service import MemoryService
from aio.orchestration.graph import run_organization
from tests.test_agents_research import (
    COMPETITOR_PAYLOAD,
    DOMAIN_PAYLOAD,
    MARKET_PAYLOAD,
    TECHNICAL_PAYLOAD,
)

BRD_PAYLOAD = {
    "vision": {
        "statement": "A focused scheduling add-on for small clinics.",
        "target_users": ["clinic front-desk staff"],
        "value_proposition": "Faster scheduling than legacy EHR modules.",
    },
    "epics": [
        {
            "title": "Account management",
            "description": "Let clinic staff create and manage accounts.",
            "user_stories": [
                {
                    "as_a": "clinic staff member",
                    "i_want": "to create an account",
                    "so_that": "I can access the scheduling tool",
                    "acceptance_criteria": [
                        "email+password required",
                        "validation errors shown inline",
                    ],
                }
            ],
        }
    ],
    "release_roadmap": [
        {"name": "MVP", "scope": "core scheduling + accounts", "epics": ["Account management"]}
    ],
    "sprint_suggestions": ["Sprint 1: auth and account management"],
    "risk_register": [
        {
            "description": "PHI leakage",
            "likelihood": "medium",
            "impact": "high",
            "mitigation": "encrypt data at rest and in transit",
        }
    ],
    "success_metrics": [
        {"name": "signup conversion", "target": "30%", "rationale": "industry benchmark"}
    ],
    "confidence": 0.8,
    "reasoning_summary": "Derived directly from the approved research report.",
}

RESEARCH_SYNTHESIS_PAYLOAD = {
    "executive_summary": "Clinic scheduling is a viable niche in a large EHR market.",
    "opportunities": ["underserved small clinics"],
    "risks": ["PHI leakage", "incumbent lock-in"],
    "assumptions": ["clinics will pay per-seat"],
    "recommended_direction": "Build a focused scheduling add-on with FHIR integration.",
    "supporting_evidence": ["EHR market sizing", "competitor feature gap in AI scribing"],
    "confidence": 0.78,
    "reasoning_summary": "Synthesized from domain, market, competitor, and technical findings.",
}


class FakeAnthropicClient:
    """Duck-typed stand-in for AnthropicClient -- no network calls.

    Routes on system prompt (which agent) and, where an agent makes more
    than one kind of call, on distinguishing text in the user prompt.
    """

    def complete(self, system: str, user: str, max_tokens: int = 2048) -> str:
        role = extract_role_from_system_prompt(system)

        if role == "Research Coordinator":
            if "research objectives" in user:
                return (
                    "- Domain Expert: identify industry and constraints\n"
                    "- Market Research: size the market and pricing\n"
                    "- Competitor Intelligence: map competing products\n"
                    "- Technical Research: survey feasible tech stacks"
                )
            if "Domain findings:" in user:
                return json.dumps(RESEARCH_SYNTHESIS_PAYLOAD)
            raise AssertionError(f"unexpected Research Coordinator prompt: {user!r}")

        if role == "JARVIS":
            if "execution plan" in user:
                return (
                    "- Research: investigate domain, market, competitors, feasibility\n"
                    "- Product: define the MVP feature set from research\n"
                    "- Engineering: propose a lean architecture"
                )
            if "APPROVE it for Product" in user:
                return "APPROVE. Research is grounded and confidence is acceptable."
            if "Product department requirements:" in user:
                return "APPROVE. Requirements and technical plan are aligned and scoped correctly."
            raise AssertionError(f"unexpected JARVIS prompt: {user!r}")

        if role == "Domain Expert":
            return json.dumps(DOMAIN_PAYLOAD)
        if role == "Market Research Analyst":
            return json.dumps(MARKET_PAYLOAD)
        if role == "Competitor Intelligence Agent":
            return json.dumps(COMPETITOR_PAYLOAD)
        if role == "Technical Research Agent":
            return json.dumps(TECHNICAL_PAYLOAD)
        if role == "Product Manager":
            return json.dumps(BRD_PAYLOAD)
        if role == "Backend Lead":
            return "Architecture: FastAPI + Postgres. Endpoints: POST /accounts, GET /accounts/{id}."

        raise AssertionError(f"unrecognized role {role!r} from system prompt: {system!r}")


def _memories(tmp_path):
    db_url = f"sqlite:///{tmp_path}/test.db"
    long_term = LongTermMemory(database_url=db_url)
    long_term.init_schema()
    semantic = SemanticMemory(location=":memory:", collection="test_projects")
    semantic.init_collection()
    memory = MemoryService(database_url=db_url)
    memory.init_schema()
    return long_term, semantic, memory


def test_run_organization_produces_full_pipeline_and_persists(tmp_path):
    long_term, semantic, memory = _memories(tmp_path)

    result = run_organization(
        goal="Launch a clinic scheduling tool",
        llm=FakeAnthropicClient(),
        long_term=long_term,
        semantic=semantic,
        memory=memory,
        # FakeAnthropicClient only stubs the research pipeline's roles;
        # the swarm stage has its own test (test_swarm.py) on the demo client.
        swarm=False,
    )

    assert "Research:" in result["ceo_plan"]

    assert result["domain_report"].industry == "Healthcare"
    assert result["market_report"].existing_products == ["Epic", "Cerner"]
    assert result["competitor_matrix"].competitors[0].name == "Epic"
    assert "FastAPI" in result["technical_report"].frameworks

    research_report = result["research_report"]
    assert research_report.executive_summary == RESEARCH_SYNTHESIS_PAYLOAD["executive_summary"]
    assert research_report.domain.industry == "Healthcare"
    assert result["research_review"].startswith("APPROVE")
    assert result["research_approved"] is True

    brd = result["business_requirements"]
    assert brd.vision.statement == BRD_PAYLOAD["vision"]["statement"]
    assert brd.epics[0].title == "Account management"

    assert "FastAPI" in result["tech_plan"]
    assert result["approved"] is True
    assert result["review"].startswith("APPROVE")
    assert "project_id" in result

    stored = long_term.get_project(result["project_id"])
    assert stored is not None
    assert stored.goal == "Launch a clinic scheduling tool"
    assert stored.research_approved is True
    assert stored.approved is True
    assert "Healthcare" in stored.research_report_json
    assert "Account management" in stored.business_requirements_json

    hits = semantic.search_similar("clinic scheduling", top_k=1)
    assert hits[0]["id"] == result["project_id"]

    # Every agent call along the pipeline should have produced an
    # execution log: ceo.plan, research_coordinator.plan, 4x research
    # agents, research_coordinator.execute, ceo.review_research,
    # product_manager.execute = 8 logged calls (ceo.review at the end
    # uses run() not run_logged, matching the pre-existing agent).
    logs = long_term.list_execution_logs()
    logged_roles = {log.agent_role for log in logs}
    assert "Domain Expert" in logged_roles
    assert "Research Coordinator" in logged_roles
    assert "Product Manager" in logged_roles

    # Roadmap item #4, step 1: the run should have recorded durable
    # organizational memory -- a RESEARCH_FINDING and (since the fake
    # research report carries risks) a consolidated RISK, both tied to this
    # project and carrying the research report's real confidence.
    entries = memory.list_entries()
    by_type = {entry.type.value: entry for entry in entries}
    assert "research_finding" in by_type
    assert "risk" in by_type
    finding = by_type["research_finding"]
    assert finding.project_id == result["project_id"]
    assert finding.department == "Research"
    assert finding.confidence == research_report.confidence
    assert research_report.executive_summary[:40] in finding.summary


def test_run_organization_without_persistence_skips_memory():
    result = run_organization(
        goal="Launch a clinic scheduling tool",
        llm=FakeAnthropicClient(),
        persist=False,
        swarm=False,
    )

    # project_id is generated up front (for event correlation) regardless
    # of persistence -- persist=False only skips writing it to the DB.
    assert result["project_id"]
    assert result["approved"] is True
    assert result["research_approved"] is True
