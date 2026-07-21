from aio.agents.base import Agent
from aio.agents.parsing import json_response_instruction
from aio.models.market_intelligence import IndexReport, ResearchPlan

class IndexResearchAgent(Agent):
    role = "Index Research Agent"
    department = "Market Intelligence"
    output_schema = IndexReport

    def execute(self, plan: ResearchPlan) -> IndexReport:
        self.system_prompt = (
            f"You are the {self.role} in the {self.department}. "
            "Your objective is to research the major indices (Nifty 50, Sensex, Bank Nifty), "
            "analyze sector composition, index weightage, and corporate actions.\n\n"
            f"{json_response_instruction(IndexReport)}"
        )
        user = f"Research Plan:\n{plan.model_dump_json(indent=2)}\n\nPlease execute your assigned tasks."
        return self.run_logged_json(user, IndexReport, handoff_target="Research Validation")
