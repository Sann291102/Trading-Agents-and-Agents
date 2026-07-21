from aio.agents.base import Agent
from aio.agents.parsing import json_response_instruction
from aio.models.market_intelligence import ResearchPlan

class ResearchPlannerAgent(Agent):
    role = "Research Planner"
    department = "Market Intelligence"
    output_schema = ResearchPlan

    def plan_research(self, goal: str) -> ResearchPlan:
        self.system_prompt = (
            f"You are the {self.role} in the {self.department}. "
            "Your job is to break down the user's market inquiry into distinct, parallel "
            "research tasks for the specialist agents.\n\n"
            "You must identify the target sectors and indices, and assign specific objectives "
            "to each relevant agent.\n\n"
            f"{json_response_instruction(ResearchPlan)}"
        )
        user = f"Market Inquiry/Goal: {goal}"
        return self.run_logged_json(user, ResearchPlan, handoff_target="Market Intelligence Specialists")
