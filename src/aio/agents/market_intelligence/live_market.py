from aio.agents.base import Agent
from aio.agents.parsing import json_response_instruction
from aio.models.market_intelligence import LiveMarketContext, ResearchPlan

class LiveMarketContextAgent(Agent):
    role = "Live Market Context Agent"
    department = "Market Intelligence"
    output_schema = LiveMarketContext

    def execute(self, plan: ResearchPlan) -> LiveMarketContext:
        self.system_prompt = (
            f"You are the {self.role} in the {self.department}. "
            "Your objective is to monitor and report on market breadth, option chains, "
            "VIX, and real-time sector rotation. Focus on observations, not trading signals.\n\n"
            f"{json_response_instruction(LiveMarketContext)}"
        )
        user = f"Research Plan:\n{plan.model_dump_json(indent=2)}\n\nPlease execute your assigned tasks."
        return self.run_logged_json(user, LiveMarketContext, handoff_target="Research Validation")
