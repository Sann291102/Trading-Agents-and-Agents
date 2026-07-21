from __future__ import annotations

from aio.agents.base import Agent
from aio.agents.parsing import json_response_instruction
from aio.models.research import (
    CompetitorMatrix,
    DomainKnowledgeReport,
    MarketResearchReport,
    ResearchReport,
    ResearchSynthesis,
    TechnicalResearchReport,
)


class ResearchCoordinatorAgent(Agent):
    """Research & Planning department lead, reporting to JARVIS.

    Breaks a business goal into research objectives for the four
    specialists (Domain Expert, Market Research, Competitor Intelligence,
    Technical Research -- run in parallel by the orchestration graph), then
    merges their findings into one unified ResearchReport: deduplicated,
    conflicts surfaced, backed by an executive summary and a recommended
    direction.

    The merge call only asks the LLM to synthesize the cross-cutting
    fields (see ResearchSynthesis) -- the four leaf reports are attached
    programmatically afterward rather than asked of the model a second
    time, since re-transcribing large nested JSON verbatim is wasteful and
    failure-prone.
    """

    role = "Research Coordinator"
    department = "Research"
    output_schema = ResearchReport
    system_prompt = (
        "You are the Research Coordinator of the organization's Research & "
        "Planning department, reporting to JARVIS. You receive "
        "findings from four specialist researchers -- domain, market, "
        "competitor, and technical -- and merge them into one synthesis: "
        "remove duplicate information, surface any conflicting conclusions "
        "as risks or assumptions, and produce an executive summary, "
        "opportunities, risks, assumptions, a recommended direction, and "
        "supporting evidence drawn from the four reports.\n\n"
        + json_response_instruction(ResearchSynthesis)
    )

    def plan(self, goal: str) -> str:
        task = (
            f"Business goal:\n{goal}\n\n"
            "List the specific research objectives to hand to each of the "
            "four specialist researchers (Domain Expert, Market Research, "
            "Competitor Intelligence, Technical Research) so their findings "
            "are directly useful for this goal. Keep it to a short bullet "
            "list, one per researcher."
        )
        text, _ = self.run_logged(
            task,
            handoff_target="Domain Expert, Market Research, Competitor Intelligence, Technical Research",
        )
        return text

    def execute(
        self,
        goal: str,
        domain: DomainKnowledgeReport,
        market: MarketResearchReport,
        competitor: CompetitorMatrix,
        technical: TechnicalResearchReport,
    ) -> ResearchReport:
        task = (
            f"Business goal:\n{goal}\n\n"
            f"Domain findings:\n{domain.model_dump_json()}\n\n"
            f"Market findings:\n{market.model_dump_json()}\n\n"
            f"Competitor findings:\n{competitor.model_dump_json()}\n\n"
            f"Technical findings:\n{technical.model_dump_json()}\n\n"
            "Synthesize these into the unified research report now."
        )
        synthesis = self.run_logged_json(task, ResearchSynthesis, handoff_target="JARVIS")
        return ResearchReport.from_synthesis(synthesis, domain, market, competitor, technical)

    def review(self, report: ResearchReport) -> str:
        sub_confidences = [
            report.domain.confidence,
            report.market.confidence,
            report.competitor.confidence,
            report.technical.confidence,
        ]
        if min(sub_confidences) < 0.4:
            return "CHANGES: at least one specialist report has low confidence"
        if report.confidence < 0.5:
            return f"CHANGES: overall confidence too low ({report.confidence})"
        return "APPROVE"

    def handoff(self, report: ResearchReport) -> dict:
        return {"research_report": report}
