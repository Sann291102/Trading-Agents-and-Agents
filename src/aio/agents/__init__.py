from .base import Agent
from .legacy.executive import ExecutiveAgent
from .legacy.product_manager import ProductManagerAgent
from .legacy.backend_lead import BackendLeadAgent
from .legacy.domain_expert import DomainExpertAgent
from .legacy.market_research import MarketResearchAgent
from .legacy.competitor_intelligence import CompetitorIntelligenceAgent
from .legacy.technical_research import TechnicalResearchAgent
from .legacy.research_coordinator import ResearchCoordinatorAgent
from .code_integrator import CodeIntegratorAgent

from .market_intelligence.market_director import MarketDirectorAgent
from .market_intelligence.research_planner import ResearchPlannerAgent
from .market_intelligence.index_research import IndexResearchAgent
from .market_intelligence.live_market import LiveMarketContextAgent
from .market_intelligence.market_psychology import MarketPsychologyAgent
from .market_intelligence.institutional_flow import InstitutionalFlowAgent
from .market_intelligence.macro_research import MacroResearchAgent
from .market_intelligence.market_memory import MarketMemoryAgent
from .market_intelligence.research_validation import ResearchValidationAgent

# Executive Business OS roster -- the founder-facing business agents.
from .business import (
    BUSINESS_AGENT_CLASSES,
    BusinessAnalystAgent,
    CampaignManagerAgent,
    ChiefOfStaffAgent,
    CompetitiveIntelligenceAgent,
    CustomerSuccessAgent,
    ExecutiveAssistantAgent,
    FinanceManagerAgent,
    GrowthManagerAgent,
    KnowledgeManagerAgent,
    MarketingDirectorAgent,
    MeetingCoordinatorAgent,
    OperationsDirectorAgent,
    SalesDirectorAgent,
    SupportManagerAgent,
)

# The 30 ruflo-imported swarm specialists (generated classes) -- imported
# for its side effect of defining the Agent subclasses, and re-exported so
# the orchestration layer can instantiate squads by role.
from .ruflo_loader import RUFLO_AGENT_CLASSES, ruflo_role_names

# Imported last -- all_agent_classes() walks Agent.__subclasses__(), which
# must already be populated by the concrete-agent imports above.
from .registry import AgentStatus, AgentStatusTracker, agent_status_tracker, all_agent_classes

__all__ = [
    "Agent",
    "ExecutiveAgent",
    "ProductManagerAgent",
    "BackendLeadAgent",
    "DomainExpertAgent",
    "MarketResearchAgent",
    "CompetitorIntelligenceAgent",
    "TechnicalResearchAgent",
    "ResearchCoordinatorAgent",
    "CodeIntegratorAgent",
    "MarketDirectorAgent",
    "ResearchPlannerAgent",
    "IndexResearchAgent",
    "LiveMarketContextAgent",
    "MarketPsychologyAgent",
    "InstitutionalFlowAgent",
    "MacroResearchAgent",
    "MarketMemoryAgent",
    "ResearchValidationAgent",
    "BUSINESS_AGENT_CLASSES",
    "ChiefOfStaffAgent",
    "ExecutiveAssistantAgent",
    "OperationsDirectorAgent",
    "MarketingDirectorAgent",
    "CampaignManagerAgent",
    "SalesDirectorAgent",
    "CustomerSuccessAgent",
    "SupportManagerAgent",
    "FinanceManagerAgent",
    "BusinessAnalystAgent",
    "GrowthManagerAgent",
    "KnowledgeManagerAgent",
    "MeetingCoordinatorAgent",
    "CompetitiveIntelligenceAgent",
    "RUFLO_AGENT_CLASSES",
    "ruflo_role_names",
    "AgentStatus",
    "AgentStatusTracker",
    "agent_status_tracker",
    "all_agent_classes",
]
