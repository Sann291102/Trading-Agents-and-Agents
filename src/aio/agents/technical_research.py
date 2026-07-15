from __future__ import annotations

from aio.agents.base import Agent
from aio.agents.parsing import json_response_instruction
from aio.models.research import TechnicalResearchReport


class TechnicalResearchAgent(Agent):
    """Research & Planning department. Surveys open-source frameworks,
    cloud services, architecture patterns, existing APIs/SDKs, integration
    possibilities, licensing, and performance benchmarks relevant to the
    goal -- feasibility research, not implementation planning (that's
    Backend Lead's job once Product Manager has turned this into
    requirements)."""

    role = "Technical Research Agent"
    department = "Research"
    output_schema = TechnicalResearchReport
    system_prompt = (
        "You are the Technical Research Agent on the organization's "
        "Research & Planning department, reporting to the Research "
        "Coordinator. Given a business goal, research relevant open-source "
        "frameworks, cloud services, architecture patterns, existing APIs "
        "and SDKs, integration possibilities, licensing considerations, and "
        "performance benchmarks. This is feasibility research, not a build "
        "plan -- leave implementation planning to Engineering.\n\n"
        + json_response_instruction(TechnicalResearchReport)
    )

    def plan(self, goal: str) -> str:
        return f"Research angle for goal '{goal}': frameworks, cloud services, APIs, feasibility."

    def execute(self, goal: str) -> TechnicalResearchReport:
        task = f"Business goal:\n{goal}\n\nProduce the technical research report now."
        return self.run_logged_json(
            task, TechnicalResearchReport, handoff_target="Research Coordinator"
        )

    def review(self, report: TechnicalResearchReport) -> str:
        if report.confidence < 0.5:
            return f"CHANGES: confidence too low ({report.confidence})"
        return "APPROVE"

    def handoff(self, report: TechnicalResearchReport) -> dict:
        return {"technical_report": report}
