import json

import pytest

from aio.agents.legacy.competitor_intelligence import CompetitorIntelligenceAgent
from aio.agents.legacy.domain_expert import DomainExpertAgent
from aio.agents.legacy.market_research import MarketResearchAgent
from aio.agents.parsing import AgentOutputParseError
from aio.agents.legacy.research_coordinator import ResearchCoordinatorAgent
from aio.agents.legacy.technical_research import TechnicalResearchAgent
from aio.models.research import (
    CompetitorMatrix,
    DomainKnowledgeReport,
    MarketResearchReport,
    TechnicalResearchReport,
)


class FakeJSONClient:
    """Duck-typed stand-in for AnthropicClient that always returns a fixed
    JSON payload, regardless of prompt -- used to unit-test one agent at a
    time without a real LLM call."""

    def __init__(self, payload: dict) -> None:
        self._text = json.dumps(payload)

    def complete(self, system: str, user: str, max_tokens: int = 2048) -> str:
        return self._text


DOMAIN_PAYLOAD = {
    "industry": "Healthcare",
    "terminology": ["EHR", "HIPAA"],
    "business_workflows": ["patient intake"],
    "compliance_concerns": ["HIPAA"],
    "industry_standards": ["HL7 FHIR"],
    "user_personas": ["clinician"],
    "business_constraints": ["must be HIPAA compliant"],
    "kpis": ["patient satisfaction"],
    "pain_points": ["manual charting"],
    "domain_risks": ["PHI leakage"],
    "confidence": 0.82,
    "reasoning_summary": "Goal mentions patient records, strongly healthcare-specific.",
}

MARKET_PAYLOAD = {
    "target_users": ["clinics"],
    "existing_products": ["Epic", "Cerner"],
    "market_size_estimate": "$40B EHR market",
    "pricing_landscape": "per-seat SaaS, $50-200/user/mo",
    "customer_expectations": ["EHR integration"],
    "emerging_trends": ["AI scribing"],
    "technology_adoption": ["cloud EHR growing"],
    "confidence": 0.7,
    "reasoning_summary": "Based on comparable EHR market sizing.",
}

COMPETITOR_PAYLOAD = {
    "competitors": [
        {
            "name": "Epic",
            "features": ["EHR", "scheduling"],
            "pricing": "enterprise contract",
            "architecture": "on-prem + cloud",
            "technology": ".NET",
            "strengths": ["market leader"],
            "weaknesses": ["expensive"],
            "differentiators": ["huge install base"],
        }
    ],
    "swot": {
        "strengths": ["faster onboarding"],
        "weaknesses": ["smaller team"],
        "opportunities": ["underserved small clinics"],
        "threats": ["incumbent lock-in"],
    },
    "feature_gaps": [
        {
            "feature": "AI scribing",
            "our_status": "planned",
            "competitor_status": "have",
            "notes": "catch-up feature",
        }
    ],
    "confidence": 0.65,
    "reasoning_summary": "Comparison based on public feature lists.",
}

TECHNICAL_PAYLOAD = {
    "frameworks": ["FastAPI", "Django"],
    "cloud_services": ["AWS HealthLake"],
    "architecture_patterns": ["event-driven"],
    "existing_apis": ["FHIR API"],
    "sdks": ["fhir.resources"],
    "integration_possibilities": ["Epic App Orchard"],
    "licensing_notes": ["FHIR spec is open"],
    "performance_benchmarks": ["FHIR server: ~500 req/s"],
    "confidence": 0.75,
    "reasoning_summary": "Based on common healthcare tech stacks.",
}


def test_domain_expert_execute_returns_parsed_report():
    agent = DomainExpertAgent(FakeJSONClient(DOMAIN_PAYLOAD))
    report = agent.execute("Build a clinic scheduling tool")

    assert isinstance(report, DomainKnowledgeReport)
    assert report.industry == "Healthcare"
    assert report.confidence == pytest.approx(0.82)
    assert agent.review(report) == "APPROVE"
    assert agent.handoff(report) == {"domain_report": report}


def test_domain_expert_review_flags_low_confidence():
    low_confidence = dict(DOMAIN_PAYLOAD, confidence=0.2)
    agent = DomainExpertAgent(FakeJSONClient(low_confidence))
    report = agent.execute("Build a clinic scheduling tool")

    assert agent.review(report).startswith("CHANGES")


def test_domain_expert_raises_on_malformed_json():
    class BrokenClient:
        def complete(self, system, user, max_tokens=2048):
            return "not json at all"

    agent = DomainExpertAgent(BrokenClient())
    with pytest.raises(AgentOutputParseError):
        agent.execute("Build a clinic scheduling tool")


def test_market_research_execute_returns_parsed_report():
    agent = MarketResearchAgent(FakeJSONClient(MARKET_PAYLOAD))
    report = agent.execute("Build a clinic scheduling tool")

    assert isinstance(report, MarketResearchReport)
    assert "Epic" in report.existing_products
    assert agent.handoff(report) == {"market_report": report}


def test_competitor_intelligence_execute_returns_parsed_matrix():
    agent = CompetitorIntelligenceAgent(FakeJSONClient(COMPETITOR_PAYLOAD))
    matrix = agent.execute("Build a clinic scheduling tool")

    assert isinstance(matrix, CompetitorMatrix)
    assert matrix.competitors[0].name == "Epic"
    assert matrix.feature_gaps[0].feature == "AI scribing"
    assert agent.review(matrix) == "APPROVE"
    assert agent.handoff(matrix) == {"competitor_matrix": matrix}


def test_competitor_intelligence_review_flags_no_competitors():
    empty = dict(COMPETITOR_PAYLOAD, competitors=[])
    agent = CompetitorIntelligenceAgent(FakeJSONClient(empty))
    matrix = agent.execute("Build a clinic scheduling tool")

    assert agent.review(matrix) == "CHANGES: no competitors identified"


def test_technical_research_execute_returns_parsed_report():
    agent = TechnicalResearchAgent(FakeJSONClient(TECHNICAL_PAYLOAD))
    report = agent.execute("Build a clinic scheduling tool")

    assert isinstance(report, TechnicalResearchReport)
    assert "FastAPI" in report.frameworks
    assert agent.handoff(report) == {"technical_report": report}


def test_research_coordinator_plan_delegates_to_llm():
    agent = ResearchCoordinatorAgent(FakeJSONClient({"ignored": True}))
    # plan() returns raw text, not parsed JSON -- FakeJSONClient's raw text
    # response is exactly what plan() should hand back unmodified.
    result = agent.plan("Build a clinic scheduling tool")
    assert result == json.dumps({"ignored": True})


def test_research_coordinator_execute_merges_reports():
    domain = DomainKnowledgeReport(**DOMAIN_PAYLOAD)
    market = MarketResearchReport(**MARKET_PAYLOAD)
    competitor = CompetitorMatrix(**COMPETITOR_PAYLOAD)
    technical = TechnicalResearchReport(**TECHNICAL_PAYLOAD)

    synthesis_payload = {
        "executive_summary": "Clinic scheduling is a viable niche in a large EHR market.",
        "opportunities": ["underserved small clinics"],
        "risks": ["PHI leakage", "incumbent lock-in"],
        "assumptions": ["clinics will pay per-seat"],
        "recommended_direction": "Build a focused scheduling add-on with FHIR integration.",
        "supporting_evidence": ["EHR market sizing", "competitor feature gap in AI scribing"],
        "confidence": 0.78,
        "reasoning_summary": "Synthesized from domain, market, competitor, and technical findings.",
    }
    agent = ResearchCoordinatorAgent(FakeJSONClient(synthesis_payload))

    report = agent.execute("Build a clinic scheduling tool", domain, market, competitor, technical)

    assert report.executive_summary == synthesis_payload["executive_summary"]
    assert report.domain == domain
    assert report.market == market
    assert report.competitor == competitor
    assert report.technical == technical
    assert agent.review(report) == "APPROVE"
    assert agent.handoff(report) == {"research_report": report}


def test_research_coordinator_review_flags_low_sub_confidence():
    domain = DomainKnowledgeReport(**dict(DOMAIN_PAYLOAD, confidence=0.1))
    market = MarketResearchReport(**MARKET_PAYLOAD)
    competitor = CompetitorMatrix(**COMPETITOR_PAYLOAD)
    technical = TechnicalResearchReport(**TECHNICAL_PAYLOAD)

    synthesis_payload = {
        "executive_summary": "summary",
        "opportunities": [],
        "risks": [],
        "assumptions": [],
        "recommended_direction": "direction",
        "supporting_evidence": [],
        "confidence": 0.9,
        "reasoning_summary": "reasoning",
    }
    agent = ResearchCoordinatorAgent(FakeJSONClient(synthesis_payload))
    report = agent.execute("goal", domain, market, competitor, technical)

    assert agent.review(report).startswith("CHANGES")
