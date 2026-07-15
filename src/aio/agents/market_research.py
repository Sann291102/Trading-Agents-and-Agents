from __future__ import annotations

from aio.agents.base import Agent
from aio.agents.parsing import json_response_instruction
from aio.models.research import MarketResearchReport


class MarketResearchAgent(Agent):
    """Research & Planning department. Researches target users, existing
    products, market size, pricing, customer expectations, emerging trends,
    and technology adoption relevant to the goal."""

    role = "Market Research Analyst"
    department = "Research"
    output_schema = MarketResearchReport
    system_prompt = (
        "You are the Market Research Analyst on the organization's Research "
        "& Planning department, reporting to the Research Coordinator. "
        "Given a business goal, research the target users, existing "
        "products serving this need, market size, pricing landscape, "
        "customer expectations, emerging trends, and technology adoption.\n\n"
        + json_response_instruction(MarketResearchReport)
    )

    def plan(self, goal: str) -> str:
        return f"Research angle for goal '{goal}': target users, market size, pricing, trends."

    def execute(self, goal: str) -> MarketResearchReport:
        task = f"Business goal:\n{goal}\n\nProduce the market research report now."
        return self.run_logged_json(
            task, MarketResearchReport, handoff_target="Research Coordinator"
        )

    def review(self, report: MarketResearchReport) -> str:
        if report.confidence < 0.5:
            return f"CHANGES: confidence too low ({report.confidence})"
        return "APPROVE"

    def handoff(self, report: MarketResearchReport) -> dict:
        return {"market_report": report}
