from aio.agents.base import Agent
from aio.agents.parsing import json_response_instruction
from aio.models.market_intelligence import MarketPsychology, ResearchPlan

class MarketPsychologyAgent(Agent):
    role = "Market Psychology Agent"
    department = "Market Intelligence"
    output_schema = MarketPsychology

    def execute(self, plan: ResearchPlan) -> MarketPsychology:
        self.system_prompt = (
            f"You are the {self.role} in the {self.department}. "
            "Your objective is to study market sentiment, fear/greed cycles, FOMO, "
            "and retail vs institutional behavioral narratives.\n\n"
            f"{json_response_instruction(MarketPsychology)}"
        )
        user = f"Research Plan:\n{plan.model_dump_json(indent=2)}\n\nPlease execute your assigned tasks."
        return self.run_logged_json(user, MarketPsychology, handoff_target="Research Validation")
