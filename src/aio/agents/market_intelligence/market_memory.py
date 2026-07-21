from aio.agents.base import Agent
from aio.agents.parsing import json_response_instruction
from aio.models.market_intelligence import MarketMemoryContext, ResearchPlan

class MarketMemoryAgent(Agent):
    role = "Market Memory Agent"
    department = "Market Intelligence"
    output_schema = MarketMemoryContext

    def execute(self, plan: ResearchPlan) -> MarketMemoryContext:
        self.system_prompt = (
            f"You are the {self.role} in the {self.department}. "
            "Your objective is to query historical knowledge, past regimes, and recurring "
            "market patterns relevant to the current inquiry.\n\n"
            f"{json_response_instruction(MarketMemoryContext)}"
        )
        user = f"Research Plan:\n{plan.model_dump_json(indent=2)}\n\nPlease execute your assigned tasks."
        return self.run_logged_json(user, MarketMemoryContext, handoff_target="Research Validation")
