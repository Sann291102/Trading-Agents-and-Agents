"""Every research/product model must round-trip through JSON -- that's the
whole point of using them as the inter-agent contract instead of prose."""

from tests.test_agents_research import (
    COMPETITOR_PAYLOAD,
    DOMAIN_PAYLOAD,
    MARKET_PAYLOAD,
    TECHNICAL_PAYLOAD,
)
from tests.test_orchestration import BRD_PAYLOAD, RESEARCH_SYNTHESIS_PAYLOAD

from aio.models.product import BusinessRequirementsDocument
from aio.models.research import (
    CompetitorMatrix,
    DomainKnowledgeReport,
    MarketResearchReport,
    ResearchReport,
    TechnicalResearchReport,
)


def _round_trip(model_cls, payload):
    instance = model_cls(**payload)
    rehydrated = model_cls.model_validate_json(instance.model_dump_json())
    assert rehydrated == instance
    return instance


def test_domain_knowledge_report_round_trips():
    _round_trip(DomainKnowledgeReport, DOMAIN_PAYLOAD)


def test_market_research_report_round_trips():
    _round_trip(MarketResearchReport, MARKET_PAYLOAD)


def test_competitor_matrix_round_trips():
    _round_trip(CompetitorMatrix, COMPETITOR_PAYLOAD)


def test_technical_research_report_round_trips():
    _round_trip(TechnicalResearchReport, TECHNICAL_PAYLOAD)


def test_business_requirements_document_round_trips():
    _round_trip(BusinessRequirementsDocument, BRD_PAYLOAD)


def test_research_report_from_synthesis_round_trips():
    domain = DomainKnowledgeReport(**DOMAIN_PAYLOAD)
    market = MarketResearchReport(**MARKET_PAYLOAD)
    competitor = CompetitorMatrix(**COMPETITOR_PAYLOAD)
    technical = TechnicalResearchReport(**TECHNICAL_PAYLOAD)

    report = ResearchReport(
        **RESEARCH_SYNTHESIS_PAYLOAD,
        domain=domain,
        market=market,
        competitor=competitor,
        technical=technical,
    )
    rehydrated = ResearchReport.model_validate_json(report.model_dump_json())
    assert rehydrated == report
