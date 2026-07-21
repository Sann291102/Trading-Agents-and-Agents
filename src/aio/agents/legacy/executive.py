from __future__ import annotations

from aio.models.research import ResearchReport

from ..base import Agent


class ExecutiveAgent(Agent):
    """JARVIS -- the organization's central intelligence. Plans delegation up
    front, reviews the Research department's findings before Product is
    allowed to act on them, and reviews final department output at the end.
    Never implements anything itself; every request flows through it first."""

    role = "JARVIS"
    department = "Executive"
    system_prompt = (
        "You are the JARVIS, the central intelligence of an autonomous AI "
        "organization. Every objective reaches you first: you analyze intent, "
        "decide what the organization needs to know, and delegate to the "
        "specialist departments best suited to deliver it. You do not write "
        "requirements or code yourself -- you make go/no-go calls on the work "
        "your departments hand back. Be decisive and concise."
    )

    def plan(self, goal: str) -> str:
        task = (
            f"A stakeholder has given the organization this goal:\n\n{goal}\n\n"
            "Write a short (3-5 bullet) execution plan describing what the "
            "Research & Planning department, the Product department, and the "
            "Engineering department should each deliver to accomplish this "
            "goal. Research must complete and be reviewed before Product "
            "writes requirements. Do not write requirements, research "
            "findings, or code yourself."
        )
        text, _ = self.run_logged(task, handoff_target="Research Coordinator")
        return text

    def review_research(self, goal: str, research_report: ResearchReport) -> str:
        task = (
            f"Original goal:\n{goal}\n\n"
            f"Research Coordinator's unified research report:\n"
            f"{research_report.model_dump_json()}\n\n"
            "Review this research. State clearly whether you APPROVE it for "
            "Product to act on or REQUEST CHANGES (e.g. more research needed, "
            "conflicting conclusions unresolved, confidence too low), and "
            "give 2-3 sentences of reasoning. Start your reply with the "
            "single word APPROVE or CHANGES."
        )
        text, _ = self.run_logged(task, handoff_target="Product Manager")
        return text

    def review(self, goal: str, requirements: str, tech_plan: str) -> str:
        task = (
            f"Original goal:\n{goal}\n\n"
            f"Product department requirements:\n{requirements}\n\n"
            f"Engineering department technical plan:\n{tech_plan}\n\n"
            "Review these deliverables. State clearly whether you APPROVE or "
            "REQUEST CHANGES, and give 2-3 sentences of reasoning. Start your "
            "reply with the single word APPROVE or CHANGES."
        )
        text, _ = self.run_logged(task)
        return text
