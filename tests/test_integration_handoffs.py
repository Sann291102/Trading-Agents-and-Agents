"""Integration tests for the four department handoffs the Research &
Planning workflow introduces. Each test wires two real agent instances
together (only the LLM is faked) and asserts the handoff contract -- the
dict/model shape one agent produces is exactly what the next consumes.
"""

from aio.agents.backend_lead import BackendLeadAgent
from aio.agents.competitor_intelligence import CompetitorIntelligenceAgent
from aio.agents.domain_expert import DomainExpertAgent
from aio.agents.executive import ExecutiveAgent
from aio.agents.market_research import MarketResearchAgent
from aio.agents.product_manager import ProductManagerAgent
from aio.agents.research_coordinator import ResearchCoordinatorAgent
from aio.agents.technical_research import TechnicalResearchAgent
from tests.test_agents_research import (
    COMPETITOR_PAYLOAD,
    DOMAIN_PAYLOAD,
    MARKET_PAYLOAD,
    TECHNICAL_PAYLOAD,
    FakeJSONClient,
)
from tests.test_orchestration import BRD_PAYLOAD, RESEARCH_SYNTHESIS_PAYLOAD


class RoutingFakeClient:
    """Returns a different canned response depending on a marker found in
    the user prompt -- lets one fake client stand in for several agents in
    the same test without them stepping on each other."""

    def __init__(self, routes: dict[str, str]) -> None:
        self._routes = routes

    def complete(self, system: str, user: str, max_tokens: int = 2048) -> str:
        for marker, response in self._routes.items():
            if marker in user or marker in system:
                return response
        raise AssertionError(f"no route matched -- system={system!r} user={user!r}")


def test_executive_ai_to_research_coordinator_handoff():
    """CEO plans the engagement, then the Research Coordinator breaks it
    into research objectives -- and later reviews/approves the
    Coordinator's merged findings."""
    ceo_client = FakeJSONClient({"ignored": True})  # plan() returns raw text, not JSON
    ceo = ExecutiveAgent(ceo_client)
    ceo_plan = ceo.plan("Build a clinic scheduling tool")
    assert ceo_plan  # CEO produced a delegation plan

    coordinator = ResearchCoordinatorAgent(FakeJSONClient({"ignored": True}))
    research_plan = coordinator.plan("Build a clinic scheduling tool")
    assert research_plan  # Coordinator turned the goal into research objectives

    # Later: CEO reviews the Coordinator's merged research report.
    from aio.models.research import (
        CompetitorMatrix,
        DomainKnowledgeReport,
        MarketResearchReport,
        ResearchReport,
        TechnicalResearchReport,
    )

    report = ResearchReport(
        **RESEARCH_SYNTHESIS_PAYLOAD,
        domain=DomainKnowledgeReport(**DOMAIN_PAYLOAD),
        market=MarketResearchReport(**MARKET_PAYLOAD),
        competitor=CompetitorMatrix(**COMPETITOR_PAYLOAD),
        technical=TechnicalResearchReport(**TECHNICAL_PAYLOAD),
    )
    ceo_with_review_client = RoutingFakeClient(
        {"APPROVE it for Product": "APPROVE. Research is sound."}
    )
    ceo2 = ExecutiveAgent(ceo_with_review_client)
    review = ceo2.review_research("Build a clinic scheduling tool", report)
    assert review.startswith("APPROVE")


def test_research_coordinator_to_research_agents_handoff():
    """The four specialist researchers each hand off a typed report via
    `.handoff()`, and the Coordinator's `.execute()` consumes exactly those
    typed objects to produce the merged ResearchReport."""
    goal = "Build a clinic scheduling tool"

    domain_agent = DomainExpertAgent(FakeJSONClient(DOMAIN_PAYLOAD))
    market_agent = MarketResearchAgent(FakeJSONClient(MARKET_PAYLOAD))
    competitor_agent = CompetitorIntelligenceAgent(FakeJSONClient(COMPETITOR_PAYLOAD))
    technical_agent = TechnicalResearchAgent(FakeJSONClient(TECHNICAL_PAYLOAD))

    domain_handoff = domain_agent.handoff(domain_agent.execute(goal))
    market_handoff = market_agent.handoff(market_agent.execute(goal))
    competitor_handoff = competitor_agent.handoff(competitor_agent.execute(goal))
    technical_handoff = technical_agent.handoff(technical_agent.execute(goal))

    coordinator = ResearchCoordinatorAgent(FakeJSONClient(RESEARCH_SYNTHESIS_PAYLOAD))
    merged = coordinator.execute(
        goal,
        domain_handoff["domain_report"],
        market_handoff["market_report"],
        competitor_handoff["competitor_matrix"],
        technical_handoff["technical_report"],
    )

    assert merged.domain.industry == "Healthcare"
    assert merged.market.existing_products == ["Epic", "Cerner"]
    assert merged.competitor.competitors[0].name == "Epic"
    assert "FastAPI" in merged.technical.frameworks
    assert coordinator.review(merged) == "APPROVE"


def test_research_coordinator_to_product_manager_handoff():
    """The Coordinator's merged ResearchReport (handed off via
    `.handoff()`) is exactly what Product Manager consumes to produce a
    BusinessRequirementsDocument -- PM never sees the raw goal alone."""
    from aio.models.research import (
        CompetitorMatrix,
        DomainKnowledgeReport,
        MarketResearchReport,
        TechnicalResearchReport,
    )

    coordinator = ResearchCoordinatorAgent(FakeJSONClient(RESEARCH_SYNTHESIS_PAYLOAD))
    merged = coordinator.execute(
        "Build a clinic scheduling tool",
        DomainKnowledgeReport(**DOMAIN_PAYLOAD),
        MarketResearchReport(**MARKET_PAYLOAD),
        CompetitorMatrix(**COMPETITOR_PAYLOAD),
        TechnicalResearchReport(**TECHNICAL_PAYLOAD),
    )
    research_handoff = coordinator.handoff(merged)

    pm = ProductManagerAgent(FakeJSONClient(BRD_PAYLOAD))
    brd = pm.execute("Build a clinic scheduling tool", research_handoff["research_report"])

    assert brd.vision.statement == BRD_PAYLOAD["vision"]["statement"]
    assert brd.epics[0].title == "Account management"
    assert pm.review(brd) == "APPROVE"


def test_product_manager_to_backend_lead_handoff():
    """PM's BusinessRequirementsDocument (handed off via `.handoff()`) is
    exactly what Backend Lead consumes to produce a technical plan --
    Engineering never sees a bare goal or free-text requirements."""
    pm = ProductManagerAgent(FakeJSONClient(BRD_PAYLOAD))
    from aio.models.research import (
        CompetitorMatrix,
        DomainKnowledgeReport,
        MarketResearchReport,
        ResearchReport,
        TechnicalResearchReport,
    )

    research_report = ResearchReport(
        **RESEARCH_SYNTHESIS_PAYLOAD,
        domain=DomainKnowledgeReport(**DOMAIN_PAYLOAD),
        market=MarketResearchReport(**MARKET_PAYLOAD),
        competitor=CompetitorMatrix(**COMPETITOR_PAYLOAD),
        technical=TechnicalResearchReport(**TECHNICAL_PAYLOAD),
    )
    brd = pm.execute("Build a clinic scheduling tool", research_report)
    pm_handoff = pm.handoff(brd)

    backend = BackendLeadAgent(
        RoutingFakeClient(
            {"Account management": "Architecture: FastAPI + Postgres. Endpoint: POST /accounts."}
        )
    )
    tech_plan = backend.plan_implementation(pm_handoff["business_requirements"])

    assert "FastAPI" in tech_plan
