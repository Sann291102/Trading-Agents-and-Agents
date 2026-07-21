from __future__ import annotations

from aio.agents.base import Agent
from aio.agents.parsing import json_response_instruction
from aio.agents.research_tools import web_research_context
from aio.models.research import DomainKnowledgeReport


class DomainExpertAgent(Agent):
    """Research & Planning department. Identifies the user's industry and
    the domain knowledge Product/Engineering will need: terminology,
    workflows, compliance concerns, standards, personas, constraints, KPIs,
    pain points, and domain-specific risks."""

    role = "Domain Expert"
    department = "Research"
    output_schema = DomainKnowledgeReport
    system_prompt = (
        "You are the Domain Expert on the organization's Research & "
        "Planning department, reporting to the Research Coordinator. Given "
        "a business goal, identify the relevant industry (e.g. healthcare, "
        "finance, education, retail, manufacturing, AI, cybersecurity, "
        "legal, real estate, government) and produce a structured domain "
        "knowledge report covering terminology, business workflows, "
        "compliance concerns, industry standards, user personas, business "
        "constraints, KPIs, pain points, and domain-specific risks.\n\n"
        + json_response_instruction(DomainKnowledgeReport)
    )

    def plan(self, goal: str) -> str:
        return (
            f"Research angle for goal '{goal}': identify industry, "
            "terminology, workflows, compliance, standards, personas, "
            "constraints, KPIs, pain points, and risks."
        )

    def execute(self, goal: str) -> DomainKnowledgeReport:
        task = (
            f"Business goal:\n{goal}\n\nProduce the domain knowledge report now."
            + web_research_context(f"{goal} industry terminology compliance standards")
        )
        return self.run_logged_json(
            task, DomainKnowledgeReport, handoff_target="Research Coordinator"
        )

    def review(self, report: DomainKnowledgeReport) -> str:
        if report.confidence < 0.5:
            return f"CHANGES: confidence too low ({report.confidence})"
        if not report.industry:
            return "CHANGES: industry not identified"
        return "APPROVE"

    def handoff(self, report: DomainKnowledgeReport) -> dict:
        return {"domain_report": report}
