from __future__ import annotations

from aio.agents.base import Agent
from aio.agents.parsing import json_response_instruction
from aio.models.research import CompetitorMatrix


class CompetitorIntelligenceAgent(Agent):
    """Research & Planning department. Identifies competing products and
    compares features, pricing, architecture, technology, strengths,
    weaknesses, and differentiators; produces a SWOT and feature-gap
    analysis."""

    role = "Competitor Intelligence Agent"
    department = "Research"
    output_schema = CompetitorMatrix
    system_prompt = (
        "You are the Competitor Intelligence Agent on the organization's "
        "Research & Planning department, reporting to the Research "
        "Coordinator. Given a business goal, identify realistic competing "
        "products and compare them on features, pricing, architecture, "
        "technology, strengths, weaknesses, and differentiators. Produce a "
        "SWOT analysis (from our prospective product's point of view) and a "
        "feature-gap analysis.\n\n" + json_response_instruction(CompetitorMatrix)
    )

    def plan(self, goal: str) -> str:
        return f"Research angle for goal '{goal}': competing products, SWOT, feature gaps."

    def execute(self, goal: str) -> CompetitorMatrix:
        task = f"Business goal:\n{goal}\n\nProduce the competitor matrix now."
        return self.run_logged_json(task, CompetitorMatrix, handoff_target="Research Coordinator")

    def review(self, report: CompetitorMatrix) -> str:
        if report.confidence < 0.5:
            return f"CHANGES: confidence too low ({report.confidence})"
        if not report.competitors:
            return "CHANGES: no competitors identified"
        return "APPROVE"

    def handoff(self, report: CompetitorMatrix) -> dict:
        return {"competitor_matrix": report}
