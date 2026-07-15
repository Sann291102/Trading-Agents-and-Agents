from .base import Agent
from .executive import ExecutiveAgent
from .product_manager import ProductManagerAgent
from .backend_lead import BackendLeadAgent
from .domain_expert import DomainExpertAgent
from .market_research import MarketResearchAgent
from .competitor_intelligence import CompetitorIntelligenceAgent
from .technical_research import TechnicalResearchAgent
from .research_coordinator import ResearchCoordinatorAgent
from .code_integrator import CodeIntegratorAgent

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
    "RUFLO_AGENT_CLASSES",
    "ruflo_role_names",
    "AgentStatus",
    "AgentStatusTracker",
    "agent_status_tracker",
    "all_agent_classes",
]
