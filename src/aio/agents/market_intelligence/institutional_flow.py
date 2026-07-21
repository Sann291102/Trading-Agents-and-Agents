from aio.agents.base import Agent
from aio.agents.parsing import json_response_instruction
from aio.models.market_intelligence import InstitutionalFlow, ResearchPlan

class InstitutionalFlowAgent(Agent):
    role = "Institutional Flow Agent"
    department = "Market Intelligence"
    output_schema = InstitutionalFlow

    def execute(self, plan: ResearchPlan) -> InstitutionalFlow:
        self.system_prompt = (
            f"You are the {self.role} in the {self.department}. "
            "Your objective is to analyze FII/DII activity, block deals, and identify "
            "institutional accumulation/distribution zones.\n\n"
            f"{json_response_instruction(InstitutionalFlow)}"
        )
        user = f"Research Plan:\n{plan.model_dump_json(indent=2)}\n\nPlease execute your assigned tasks."
        return self.run_logged_json(user, InstitutionalFlow, handoff_target="Research Validation")
