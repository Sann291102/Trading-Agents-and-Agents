from aio.agents.base import Agent
from aio.agents.parsing import json_response_instruction
from aio.models.market_intelligence import MacroContext, ResearchPlan

class MacroResearchAgent(Agent):
    role = "Macro Research Agent"
    department = "Market Intelligence"
    output_schema = MacroContext

    def execute(self, plan: ResearchPlan) -> MacroContext:
        self.system_prompt = (
            f"You are the {self.role} in the {self.department}. "
            "Your objective is to analyze macroeconomic context, global cues, domestic indicators, "
            "and the impact of currencies and commodities on the Indian market.\n\n"
            f"{json_response_instruction(MacroContext)}"
        )
        user = f"Research Plan:\n{plan.model_dump_json(indent=2)}\n\nPlease execute your assigned tasks."
        return self.run_logged_json(user, MacroContext, handoff_target="Research Validation")
