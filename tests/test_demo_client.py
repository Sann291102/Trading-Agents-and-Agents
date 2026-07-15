"""Verifies the demo LLM provider produces schema-valid output for every
agent -- this is what lets Phase 3's real event pipeline / frontend be
demoed end-to-end without a paid Anthropic key (see llm/demo_client.py)."""

from aio.agents import (
    BackendLeadAgent,
    CompetitorIntelligenceAgent,
    DomainExpertAgent,
    ExecutiveAgent,
    MarketResearchAgent,
    ProductManagerAgent,
    ResearchCoordinatorAgent,
    TechnicalResearchAgent,
)
from aio.llm.demo_client import DemoAnthropicClient
from aio.memory.long_term import LongTermMemory
from aio.memory.semantic import SemanticMemory
from aio.memory.service import MemoryService
from aio.models.product import BusinessRequirementsDocument
from aio.models.research import (
    CompetitorMatrix,
    DomainKnowledgeReport,
    MarketResearchReport,
    ResearchReport,
    TechnicalResearchReport,
)
from aio.orchestration.graph import run_organization

GOAL = "Launch a customer feedback widget for a SaaS dashboard"


def test_domain_expert_execute_produces_valid_report():
    agent = DomainExpertAgent(DemoAnthropicClient())
    report = agent.execute(GOAL)
    assert isinstance(report, DomainKnowledgeReport)
    assert 0.0 <= report.confidence <= 1.0


def test_market_research_execute_produces_valid_report():
    agent = MarketResearchAgent(DemoAnthropicClient())
    report = agent.execute(GOAL)
    assert isinstance(report, MarketResearchReport)


def test_competitor_intelligence_execute_produces_valid_matrix():
    agent = CompetitorIntelligenceAgent(DemoAnthropicClient())
    matrix = agent.execute(GOAL)
    assert isinstance(matrix, CompetitorMatrix)
    assert matrix.competitors


def test_technical_research_execute_produces_valid_report():
    agent = TechnicalResearchAgent(DemoAnthropicClient())
    report = agent.execute(GOAL)
    assert isinstance(report, TechnicalResearchReport)


def test_research_coordinator_plan_and_execute():
    llm = DemoAnthropicClient()
    coordinator = ResearchCoordinatorAgent(llm)
    plan = coordinator.plan(GOAL)
    assert isinstance(plan, str) and plan

    domain = DomainExpertAgent(llm).execute(GOAL)
    market = MarketResearchAgent(llm).execute(GOAL)
    competitor = CompetitorIntelligenceAgent(llm).execute(GOAL)
    technical = TechnicalResearchAgent(llm).execute(GOAL)

    report = coordinator.execute(GOAL, domain, market, competitor, technical)
    assert isinstance(report, ResearchReport)
    assert report.domain is domain


def test_executive_plan_review_research_and_review():
    llm = DemoAnthropicClient()
    ceo = ExecutiveAgent(llm)
    assert ceo.plan(GOAL)

    coordinator = ResearchCoordinatorAgent(llm)
    domain = DomainExpertAgent(llm).execute(GOAL)
    market = MarketResearchAgent(llm).execute(GOAL)
    competitor = CompetitorIntelligenceAgent(llm).execute(GOAL)
    technical = TechnicalResearchAgent(llm).execute(GOAL)
    report = coordinator.execute(GOAL, domain, market, competitor, technical)

    assert ceo.review_research(GOAL, report).upper().startswith("APPROVE")

    brd_llm = DemoAnthropicClient()
    brd = ProductManagerAgent(brd_llm).execute(GOAL, report)
    tech_plan = BackendLeadAgent(brd_llm).plan_implementation(brd)
    assert ceo.review(GOAL, brd.model_dump_json(), tech_plan).upper().startswith("APPROVE")


def test_product_manager_execute_produces_valid_brd():
    llm = DemoAnthropicClient()
    coordinator = ResearchCoordinatorAgent(llm)
    domain = DomainExpertAgent(llm).execute(GOAL)
    market = MarketResearchAgent(llm).execute(GOAL)
    competitor = CompetitorIntelligenceAgent(llm).execute(GOAL)
    technical = TechnicalResearchAgent(llm).execute(GOAL)
    report = coordinator.execute(GOAL, domain, market, competitor, technical)

    brd = ProductManagerAgent(llm).execute(GOAL, report)
    assert isinstance(brd, BusinessRequirementsDocument)
    assert brd.epics


def test_full_pipeline_runs_end_to_end_with_demo_client(tmp_path):
    db_url = f"sqlite:///{tmp_path}/test.db"
    long_term = LongTermMemory(database_url=db_url)
    long_term.init_schema()
    semantic = SemanticMemory(location=":memory:", collection="test_demo_projects")
    semantic.init_collection()
    memory = MemoryService(database_url=db_url)
    memory.init_schema()

    result = run_organization(
        GOAL,
        llm=DemoAnthropicClient(),
        long_term=long_term,
        semantic=semantic,
        memory=memory,
    )

    assert result["approved"] is True
    assert result["research_approved"] is True
    assert result["research_report"].executive_summary
    assert result["business_requirements"].epics

    stored = long_term.get_project(result["project_id"])
    assert stored is not None
    assert stored.approved is True
