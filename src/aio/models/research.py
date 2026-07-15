"""Structured outputs for the Research & Planning department.

Every research agent returns one of these instead of free text, so
downstream agents (and the API) get a typed, serializable contract instead
of having to re-parse prose. `confidence` and `reasoning_summary` are on
every leaf report so the observability layer can log them without a
separate extraction step -- the agent's LLM call is instructed to fill
them in as part of its normal JSON output.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DomainKnowledgeReport(BaseModel):
    industry: str
    terminology: list[str] = Field(default_factory=list)
    business_workflows: list[str] = Field(default_factory=list)
    compliance_concerns: list[str] = Field(default_factory=list)
    industry_standards: list[str] = Field(default_factory=list)
    user_personas: list[str] = Field(default_factory=list)
    business_constraints: list[str] = Field(default_factory=list)
    kpis: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    domain_risks: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str


class MarketResearchReport(BaseModel):
    target_users: list[str] = Field(default_factory=list)
    existing_products: list[str] = Field(default_factory=list)
    market_size_estimate: str = ""
    pricing_landscape: str = ""
    customer_expectations: list[str] = Field(default_factory=list)
    emerging_trends: list[str] = Field(default_factory=list)
    technology_adoption: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str


class CompetitorProfile(BaseModel):
    name: str
    features: list[str] = Field(default_factory=list)
    pricing: str = ""
    architecture: str = ""
    technology: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    differentiators: list[str] = Field(default_factory=list)


class FeatureGap(BaseModel):
    feature: str
    our_status: str  # e.g. "missing", "partial", "planned", "have"
    competitor_status: str
    notes: str = ""


class SWOTAnalysis(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    threats: list[str] = Field(default_factory=list)


class CompetitorMatrix(BaseModel):
    competitors: list[CompetitorProfile] = Field(default_factory=list)
    swot: SWOTAnalysis
    feature_gaps: list[FeatureGap] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str


class TechnicalResearchReport(BaseModel):
    frameworks: list[str] = Field(default_factory=list)
    cloud_services: list[str] = Field(default_factory=list)
    architecture_patterns: list[str] = Field(default_factory=list)
    existing_apis: list[str] = Field(default_factory=list)
    sdks: list[str] = Field(default_factory=list)
    integration_possibilities: list[str] = Field(default_factory=list)
    licensing_notes: list[str] = Field(default_factory=list)
    performance_benchmarks: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str


class ResearchSynthesis(BaseModel):
    """What the Research Coordinator's LLM call actually generates: the
    cross-cutting synthesis. The four leaf reports are attached in Python
    (see `ResearchCoordinatorAgent.execute`) rather than asking the LLM to
    faithfully retranscribe them, which would be redundant and error-prone."""

    executive_summary: str
    opportunities: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    recommended_direction: str
    supporting_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str


class ResearchReport(BaseModel):
    executive_summary: str
    opportunities: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    recommended_direction: str
    supporting_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str
    domain: DomainKnowledgeReport
    market: MarketResearchReport
    competitor: CompetitorMatrix
    technical: TechnicalResearchReport

    @classmethod
    def from_synthesis(
        cls,
        synthesis: ResearchSynthesis,
        domain: DomainKnowledgeReport,
        market: MarketResearchReport,
        competitor: CompetitorMatrix,
        technical: TechnicalResearchReport,
    ) -> "ResearchReport":
        return cls(
            **synthesis.model_dump(),
            domain=domain,
            market=market,
            competitor=competitor,
            technical=technical,
        )
