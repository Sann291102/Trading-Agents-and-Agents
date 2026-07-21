from typing import Any, Optional
from pydantic import BaseModel, Field

class MarketIntelligenceBase(BaseModel):
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in this assessment (0-1)")
    reasoning_summary: str = Field(..., description="Brief summary of how this conclusion was reached")

class ResearchTask(BaseModel):
    agent_role: str = Field(..., description="The role of the agent assigned to this task")
    objective: str = Field(..., description="Specific objective for this research task")
    required_outputs: list[str] = Field(..., description="List of expected output formats or data points")

class ResearchPlan(MarketIntelligenceBase):
    goal: str = Field(..., description="The overarching market intelligence goal")
    tasks: list[ResearchTask] = Field(..., description="Delegated tasks for specialist agents")
    target_sectors: list[str] = Field(default_factory=list, description="Target market sectors identified")
    target_indices: list[str] = Field(default_factory=list, description="Target indices identified")

class IndexReport(MarketIntelligenceBase):
    index_name: str
    current_status: str
    key_drivers: list[str]
    corporate_actions: list[str]
    support_resistance_levels: dict[str, float] = Field(default_factory=dict)

class LiveMarketContext(MarketIntelligenceBase):
    market_breadth: str
    option_chain_summary: str
    vix_status: str
    sector_rotation: list[str]
    key_observations: list[str]

class MarketPsychology(MarketIntelligenceBase):
    retail_sentiment: str
    institutional_sentiment: str
    fear_greed_index_proxy: float
    dominant_narratives: list[str]

class InstitutionalFlow(MarketIntelligenceBase):
    fii_activity: str
    dii_activity: str
    notable_block_deals: list[str]
    accumulation_distribution_zones: list[str]

class MacroContext(MarketIntelligenceBase):
    global_cues: list[str]
    domestic_indicators: list[str]
    rbi_policy_stance: str
    currency_commodity_impact: str

class MarketMemoryContext(MarketIntelligenceBase):
    historical_similarities: list[str]
    past_regimes: list[str]
    recurring_patterns: list[str]

class MarketIntelligenceReport(MarketIntelligenceBase):
    executive_summary: str
    index_context: Optional[IndexReport] = None
    live_market_context: Optional[LiveMarketContext] = None
    psychology_context: Optional[MarketPsychology] = None
    institutional_flow: Optional[InstitutionalFlow] = None
    macro_context: Optional[MacroContext] = None
    memory_context: Optional[MarketMemoryContext] = None
    synthesis: str = Field(..., description="Synthesized conclusion from all parallel research")
    key_risks: list[str] = Field(default_factory=list)
    actionable_insights: list[str] = Field(default_factory=list)
