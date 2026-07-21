"""JARVIS putting its own employees to work.

This is the difference between an assistant and an operator. Every other
capability moves a row in JARVIS's database; these two actually spend an
LLM call getting a named business agent to produce work, and hand the real
output back on the ActionResult so the founder reads what the Sales
Director wrote, not a note saying the Sales Director was asked.

Delegation is SAFE: the output stays inside JARVIS (activity feed and
organizational memory), nothing is sent anywhere and nothing is spent
beyond the model call. Publishing or emailing what an agent produced is a
separate, SENSITIVE action.

Two rules keep the output trustworthy. The role is validated against the
real roster *before* any model is built, because a delegation to an
invented "Product Agent" would otherwise burn a call and then fail. And
every agent is grounded with `snapshot_for_briefing()` -- without the real
company state, an agent asked about a pre-revenue company will happily
invent revenue for it.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from aio.actions.base import ActionContext, ActionOutcome, ActionResult, ActionRisk
from aio.actions.catalog.business_ops import (
    resolve_agent_role,
    resolve_company,
    roster_names,
    unknown_company,
)
from aio.actions.registry import action
from aio.agents.business import BUSINESS_AGENT_CLASSES
from aio.events.bus import OrgEvent, event_bus
from aio.llm import build_default_llm

logger = logging.getLogger("aio.actions.delegation")

_SUMMARY_PREVIEW = 140


def _agent_class(role: str):
    canonical = resolve_agent_role(role)
    if canonical is None:
        return None
    return next(cls for cls in BUSINESS_AGENT_CLASSES if cls.role == canonical)


def _unknown_agent(role: str) -> ActionResult:
    return ActionResult(
        outcome=ActionOutcome.FAILED,
        summary=f"There is no agent called {role!r} to give that to",
        detail=f"Valid agents: {roster_names()}.",
    )


def _remember(context: ActionContext, *, title: str, role: str, department: str, output: str) -> bool:
    """File an agent's output into organizational memory.

    Best-effort on purpose: the work is already done and recorded by the
    executor by the time this runs, so a memory backend that is absent or
    broken must not turn a successful delegation into a failure.
    """
    if context.memory is None:
        return False
    try:
        from aio.models.memory import MemoryEntry, MemoryMetadata, MemoryType

        context.memory.create_entry(
            MemoryEntry(
                title=title,
                type=MemoryType.RESEARCH_FINDING,
                summary=output,
                department=department,
                owner=role,
                confidence=0.6,
                metadata=MemoryMetadata(
                    tags=["delegation", role],
                    source_agent=context.actor,
                ),
            )
        )
        return True
    except Exception:
        logger.warning("could not file %s output to organizational memory", role, exc_info=True)
        return False


def _run_agent(
    context: ActionContext,
    *,
    role: str,
    task: str,
    company_name: str,
    memory_title: str,
    summary_verb: str,
) -> ActionResult:
    """Shared body of both delegation actions: validate, ground, execute,
    announce, remember."""
    cls = _agent_class(role)
    if cls is None:
        return _unknown_agent(role)

    instruction = task.strip()
    if not instruction:
        return ActionResult(
            outcome=ActionOutcome.FAILED,
            summary=f"Nothing to give {cls.role} -- the task was empty",
        )

    company = None
    if company_name:
        company = resolve_company(context.business, company_name)
        if company is None:
            return unknown_company(context.business, company_name)
        instruction = f"[Company: {company.name}] {instruction}"

    grounding = context.business.snapshot_for_briefing()
    agent = cls(build_default_llm(), long_term=context.long_term)
    output = agent.execute(instruction, context=grounding)

    event_bus.publish(
        OrgEvent(
            type="task_delegated",
            agent_role=cls.role,
            department=cls.department,
            message=f"{context.actor} gave {cls.role} a task: {instruction[:_SUMMARY_PREVIEW]}",
            payload={"task": instruction, "company": company.name if company else ""},
        )
    )

    filed = _remember(
        context,
        title=memory_title.format(role=cls.role, task=instruction[:80]),
        role=cls.role,
        department=cls.department,
        output=output,
    )

    scope = f" on {company.name}" if company else ""
    preview = (
        instruction
        if len(instruction) <= _SUMMARY_PREVIEW
        else instruction[: _SUMMARY_PREVIEW - 1] + "…"
    )
    return ActionResult(
        outcome=ActionOutcome.EXECUTED,
        summary=f"{summary_verb} {cls.role}{scope}: {preview}",
        detail=output,
        data={
            "agent_role": cls.role,
            "department": cls.department,
            "company": company.name if company else "",
            "output": output,
            "filed_to_memory": filed,
        },
    )


# -- delegate_to_agent -------------------------------------------------------


class DelegateToAgentParams(BaseModel):
    agent_role: str = Field(
        ...,
        description=f"Which business agent does the work -- verbatim from: {roster_names()}",
    )
    task: str = Field(..., description="What they must do, phrased as a direct instruction")
    company_name: str = Field("", description="Company this work is for, if it is company-specific")


@action(
    "delegate_to_agent",
    description="Give a task to a business agent and get their work back",
    risk=ActionRisk.SAFE,
    params_model=DelegateToAgentParams,
    owner_agent="Chief of Staff",
)
def delegate_to_agent(context: ActionContext, params: DelegateToAgentParams) -> ActionResult:
    return _run_agent(
        context,
        role=params.agent_role,
        task=params.task,
        company_name=params.company_name,
        memory_title="{role} delivered: {task}",
        summary_verb="Delegated to",
    )


# -- request_agent_report ----------------------------------------------------


class RequestAgentReportParams(BaseModel):
    agent_role: str = Field(
        ...,
        description=f"Which business agent reports -- verbatim from: {roster_names()}",
    )
    topic: str = Field(..., description="What to report on, e.g. 'pipeline health this month'")
    company_name: str = Field("", description="Company the report is about, if specific")


@action(
    "request_agent_report",
    description="Ask a business agent for a short status or analysis on a topic",
    risk=ActionRisk.SAFE,
    params_model=RequestAgentReportParams,
    owner_agent="Chief of Staff",
)
def request_agent_report(context: ActionContext, params: RequestAgentReportParams) -> ActionResult:
    topic = params.topic.strip()
    task = (
        f"Report on: {topic}. Give the founder your read in under 150 words: "
        "where this stands, what changed, and the one thing you would do next. "
        "Use only what the business context supports."
    ) if topic else ""
    return _run_agent(
        context,
        role=params.agent_role,
        task=task,
        company_name=params.company_name,
        memory_title="{role} report: {task}",
        summary_verb="Got a report from",
    )
