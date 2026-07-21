"""The Executive Business OS agent roster.

JARVIS serves the founder, not customers. These agents replace the
developer-focused departments as the primary org: each is a real
`Agent` subclass (so it auto-appears in `GET /agents` and the frontend
roster via the registry) with a working `execute(task)` grounded in
whatever business context the caller passes.

Two agents carry the core product surface today:
- `ChiefOfStaffAgent.briefing(context)` -> structured `ExecutiveBriefing`
  (headline, health, priorities, risks, opportunities) for the dashboard.
- `ExecutiveAssistantAgent.converse(message, context)` -> conversational
  reply powering the voice-first assistant bar.

Every other director/manager has a focused system prompt and a shared
`execute` implementation, so any of them can be given a task directly
(via the assistant or future delegation flows) and produce useful,
logged, observable output through the same run_logged pipeline the rest
of the org uses.
"""

from __future__ import annotations

from aio.agents.base import Agent
from aio.agents.parsing import json_response_instruction
from aio.models.business import (
    AssistantReply,
    ConversationTurn,
    ExecutiveBriefing,
    LaunchPlan,
)


def business_roster_names() -> str:
    """The roles an agent may assign work to, as a comma-separated list.

    Fed into the Chief of Staff's prompts because a model left to invent
    owner names does exactly that -- real runs produced "Product Agent" and
    "Engineering Agent", neither of which exists, so the resulting milestone
    could never actually be delegated. Built from the roster itself so it
    cannot drift as agents are added.
    """
    return ", ".join(cls.role for cls in BUSINESS_AGENT_CLASSES)


class BusinessAgent(Agent):
    """Shared behavior: every business agent can execute a free-form task
    with its role-specific system prompt and full observability."""

    focus: str = ""  # one-line role charter, used to build the system prompt

    def execute(self, task: str, context: str = "") -> str:
        self.system_prompt = (
            f"You are the {self.role} for a founder's holding organization. "
            f"{self.focus} Be concrete, brief, and action-oriented -- you are "
            "writing for a busy founder, not producing a report. When business "
            "context is provided, ground every statement in it; never invent numbers."
        )
        user = (f"Business context:\n{context}\n\nTask: {task}") if context else f"Task: {task}"
        text, _ = self.run_logged(user)
        return text


class ChiefOfStaffAgent(BusinessAgent):
    role = "Chief of Staff"
    department = "Executive Office"
    focus = "You run the founder's day: synthesize company state, set priorities, flag risks."
    output_schema = ExecutiveBriefing

    def briefing(self, context: str) -> ExecutiveBriefing:
        """The morning executive briefing, grounded in the real company
        snapshot assembled by BusinessService.snapshot_for_briefing()."""
        self.system_prompt = (
            "You are the Chief of Staff for a founder building and operating "
            "one or more companies. Compose today's executive briefing "
            "strictly from the business context provided -- never invent "
            "metrics that are not present.\n\n"
            "Companies marked PRE-REVENUE have not launched: they have no "
            "customers, no revenue, and no MRR. For those, do not discuss "
            "growth rates, churn, runway, or any financial metric -- there is "
            "nothing to measure yet. Judge them only on progress toward "
            "launch: what has shipped, what is blocked, what must happen next "
            "to get a working product in front of the first real user. "
            "business_health for a pre-revenue company reflects whether it is "
            "moving toward launch, not whether it is profitable.\n\n"
            "Every priority's owner_agent MUST be chosen verbatim from this "
            "roster -- these are the only agents that exist:\n"
            f"{business_roster_names()}\n\n"
            f"{json_response_instruction(ExecutiveBriefing)}"
        )
        user = f"Current business context:\n{context}\n\nProduce today's executive briefing."
        return self.run_logged_json(user, ExecutiveBriefing, handoff_target="Founder")

    def launch_plan(self, company_name: str, target_stage: str, context: str) -> LaunchPlan:
        """Decompose "get this company to its next stage" into concrete,
        owned milestones. This is what JARVIS produces for a company with no
        revenue yet -- the plan to build one, not a report on one."""
        self.system_prompt = (
            "You are the Chief of Staff for a founder taking a company from "
            "nothing to a real business. Your job right now is the plan, not "
            "a status report.\n\n"
            "Given the company's actual state, lay out the milestones that "
            "move it to the target stage. Rules: every milestone must be "
            "concrete enough to know when it is done (not 'improve "
            "marketing'); order them so each unblocks the next; assign each "
            "to the business agent who should drive it; keep the list short "
            "enough to actually execute (4-7 items). Never assume budget, "
            "team, or traction that the context does not mention. If the "
            "company has already completed milestones, build on them rather "
            "than repeating them.\n\n"
            "owner_agent MUST be chosen verbatim from this roster -- these "
            "are the only agents that exist, and an invented name cannot be "
            "given the work:\n"
            f"{business_roster_names()}\n\n"
            f"{json_response_instruction(LaunchPlan)}"
        )
        user = (
            f"Business context:\n{context}\n\n"
            f"Plan how to get {company_name} to the '{target_stage}' stage."
        )
        return self.run_logged_json(user, LaunchPlan, handoff_target="Founder")


class ExecutiveAssistantAgent(BusinessAgent):
    role = "Executive Assistant"
    department = "Executive Office"
    focus = "You are the founder's always-on conversational interface to the whole organization."
    output_schema = AssistantReply

    def converse(
        self,
        message: str,
        context: str,
        history: list[ConversationTurn] | None = None,
    ) -> AssistantReply:
        self.system_prompt = (
            "You are the Executive Assistant, JARVIS, the founder's always-on "
            "voice interface to the whole organization. You are speaking with "
            "them directly (often by voice, so keep replies natural, spoken-"
            "style, and under 120 words unless detail is explicitly asked for). "
            "Ground answers in the business context provided; never invent "
            "numbers. Companies marked PRE-REVENUE have not launched -- they "
            "have no customers, revenue, or MRR. If asked how one is doing, "
            "answer in terms of progress toward launch and say plainly that "
            "there are no numbers yet; never produce a figure to fill the "
            "gap. Use the conversation so far to stay coherent -- resolve "
            "pronouns and follow-ups against it. If the founder asks for work "
            "that a specialist should own, name that agent in "
            "suggested_actions (e.g. 'Ask the Sales Director to draft the "
            "outreach sequence').\n\n"
            f"{json_response_instruction(AssistantReply)}"
        )
        parts = [f"Business context:\n{context}"]
        if history:
            transcript = "\n".join(
                f"{'Founder' if turn.who == 'founder' else 'JARVIS'}: {turn.text}"
                for turn in history[-12:]
            )
            parts.append(f"Conversation so far:\n{transcript}")
        parts.append(f"Founder says: {message}")
        return self.run_logged_json("\n\n".join(parts), AssistantReply, handoff_target="Founder")

    def greet(self, context: str) -> AssistantReply:
        """The spoken greeting when the founder opens JARVIS: acknowledge
        them, surface what matters right now (numbers, pending decisions),
        all grounded in the same live business snapshot."""
        self.system_prompt = (
            "You are the Executive Assistant, JARVIS, greeting the founder as "
            "they arrive. Compose a short spoken-style greeting (2-4 "
            "sentences, under 70 words): welcome them, then surface the one "
            "or two things that most deserve attention right now from the "
            "business context -- pending decisions first, then notable "
            "numbers. Ground everything in the context provided; never "
            "invent data. If there is nothing notable, say the desk is "
            "clear. Offer next steps in suggested_actions.\n\n"
            f"{json_response_instruction(AssistantReply)}"
        )
        user = f"Business context:\n{context}\n\nGreet the founder."
        return self.run_logged_json(user, AssistantReply, handoff_target="Founder")


class OperationsDirectorAgent(BusinessAgent):
    role = "Operations Director"
    department = "Operations"
    focus = "You keep the companies running: processes, vendors, hiring ops, execution cadence."


class MarketingDirectorAgent(BusinessAgent):
    role = "Marketing Director"
    department = "Marketing"
    focus = "You own positioning, brand, channels, and the marketing plan across companies."


class CampaignManagerAgent(BusinessAgent):
    role = "Campaign Manager"
    department = "Marketing"
    focus = "You design and run individual campaigns: audience, creative brief, budget, schedule."


class SalesDirectorAgent(BusinessAgent):
    role = "Sales Director"
    department = "Sales"
    focus = "You own pipeline, outreach, pricing conversations, and closing revenue."


class CustomerSuccessAgent(BusinessAgent):
    role = "Customer Success"
    department = "Customer"
    focus = "You own onboarding, retention, expansion, and the voice of the customer."


class SupportManagerAgent(BusinessAgent):
    role = "Support Manager"
    department = "Customer"
    focus = "You own support quality: ticket trends, response playbooks, escalation triage."


class FinanceManagerAgent(BusinessAgent):
    role = "Finance Manager"
    department = "Finance"
    focus = "You own cash, burn, runway, pricing economics, and financial hygiene."


class BusinessAnalystAgent(BusinessAgent):
    role = "Business Analyst"
    department = "Analytics"
    focus = "You turn raw metrics into insight: trends, cohorts, anomalies, what changed and why."


class GrowthManagerAgent(BusinessAgent):
    role = "Growth Manager"
    department = "Growth"
    focus = "You find and test growth levers: funnels, activation, referral loops, experiments."


class KnowledgeManagerAgent(BusinessAgent):
    role = "Knowledge Manager"
    department = "Knowledge"
    focus = "You keep organizational memory organized, current, and retrievable."


class MeetingCoordinatorAgent(BusinessAgent):
    role = "Meeting Coordinator"
    department = "Executive Office"
    focus = "You prepare agendas, capture decisions, and track follow-ups from meetings."


class CompetitiveIntelligenceAgent(BusinessAgent):
    role = "Competitive Intelligence"
    department = "Strategy"
    focus = "You track competitors, market moves, and strategic threats/openings."


BUSINESS_AGENT_CLASSES: list[type[BusinessAgent]] = [
    ChiefOfStaffAgent,
    ExecutiveAssistantAgent,
    OperationsDirectorAgent,
    MarketingDirectorAgent,
    CampaignManagerAgent,
    SalesDirectorAgent,
    CustomerSuccessAgent,
    SupportManagerAgent,
    FinanceManagerAgent,
    BusinessAnalystAgent,
    GrowthManagerAgent,
    KnowledgeManagerAgent,
    MeetingCoordinatorAgent,
    CompetitiveIntelligenceAgent,
]
