from __future__ import annotations

from aio.agents.parsing import json_response_instruction
from aio.models.product import BusinessRequirementsDocument
from aio.models.research import ResearchReport

from .base import Agent


class ProductManagerAgent(Agent):
    """Product Division.

    As of the Research & Planning department's introduction, the Product
    Manager no longer turns a raw business goal into requirements directly
    -- decisions must be grounded in the Executive-approved ResearchReport
    (domain knowledge, market research, competitor intelligence, technical
    feasibility), not assumptions. It now produces a full Business
    Requirements Document: product vision, epics, user stories with
    acceptance criteria, a release roadmap, sprint suggestions, a risk
    register, and success metrics.
    """

    role = "Product Manager"
    department = "Product"
    output_schema = BusinessRequirementsDocument
    system_prompt = (
        "You are the Product Manager of the Product department. You do not "
        "invent requirements from assumptions -- you receive a research "
        "report (domain knowledge, market research, competitor "
        "intelligence, technical feasibility) that JARVIS has "
        "already reviewed and approved, and you turn it into a full "
        "Business Requirements Document: a product vision, epics containing "
        "user stories (each with 2-3 acceptance criteria), a release "
        "roadmap, sprint suggestions, a risk register, and success metrics. "
        "Be concrete and scoped to what is achievable in a first release. "
        "Do not propose technical implementation details -- that is "
        "Engineering's job.\n\n" + json_response_instruction(BusinessRequirementsDocument)
    )

    def plan(self, goal: str, research_report: ResearchReport) -> str:
        return (
            f"Business goal: {goal}\n"
            f"Recommended direction from research: {research_report.recommended_direction}\n"
            "Plan: derive product vision, epics/stories, roadmap, risks, "
            "and success metrics from the research report, not from the "
            "goal alone."
        )

    def execute(self, goal: str, research_report: ResearchReport) -> BusinessRequirementsDocument:
        task = (
            f"Business goal:\n{goal}\n\n"
            f"Executive-approved research report:\n{research_report.model_dump_json()}\n\n"
            "Produce the Business Requirements Document now, grounded in "
            "the research above."
        )
        return self.run_logged_json(task, BusinessRequirementsDocument, handoff_target="Backend Lead")

    def review(self, brd: BusinessRequirementsDocument) -> str:
        if brd.confidence < 0.5:
            return f"CHANGES: confidence too low ({brd.confidence})"
        if not brd.epics:
            return "CHANGES: no epics produced"
        return "APPROVE"

    def handoff(self, brd: BusinessRequirementsDocument) -> dict:
        return {"business_requirements": brd}
