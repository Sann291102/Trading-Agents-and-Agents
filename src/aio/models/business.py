"""Pydantic contracts for the Executive Business Operating System.

JARVIS manages *companies* (TradeW is the first). Every hand-off between
business agents and the API uses these models, mirroring how
models/research.py works for the legacy engineering pipeline.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# The lifecycle JARVIS walks a company through, in order. Everything before
# "launched" is pre-revenue: there are no customers or MRR to report yet, so
# JARVIS runs the company by milestones (what must ship to reach the next
# stage) rather than by metrics.
COMPANY_STAGES = ["idea", "building", "launched", "operating", "scaling"]
PRE_REVENUE_STAGES = {"idea", "building"}


def next_stage(stage: str) -> str | None:
    """The stage after `stage`, or None at the end of the ladder."""
    if stage not in COMPANY_STAGES:
        return None
    index = COMPANY_STAGES.index(stage)
    return COMPANY_STAGES[index + 1] if index + 1 < len(COMPANY_STAGES) else None


class Company(BaseModel):
    id: str = Field(default_factory=_uuid)
    name: str
    description: str = ""
    industry: str = ""
    stage: str = "idea"  # see COMPANY_STAGES
    website: str = ""
    created_at: datetime = Field(default_factory=_now)

    @property
    def is_pre_revenue(self) -> bool:
        return self.stage in PRE_REVENUE_STAGES


class BusinessMetricSnapshot(BaseModel):
    """One point-in-time snapshot of a company's core numbers. Recorded by
    the operator (or later by connectors) and read by the dashboard and the
    Chief of Staff when composing the executive briefing."""

    id: str = Field(default_factory=_uuid)
    company_id: str
    mrr: float = 0.0                  # monthly recurring revenue
    revenue_this_month: float = 0.0
    customers: int = 0
    new_customers_this_month: int = 0
    churned_customers_this_month: int = 0
    active_users: int = 0
    support_open_tickets: int = 0
    marketing_spend_this_month: float = 0.0
    sales_pipeline_value: float = 0.0
    cash_balance: float = 0.0
    burn_rate_monthly: float = 0.0
    notes: str = ""
    recorded_at: datetime = Field(default_factory=_now)


class Approval(BaseModel):
    """A decision waiting on the founder. Business agents raise these; the
    dashboard surfaces them; the operator approves or rejects."""

    id: str = Field(default_factory=_uuid)
    company_id: str | None = None
    title: str
    detail: str = ""
    requested_by: str = "Chief of Staff"
    status: Literal["pending", "approved", "rejected"] = "pending"
    created_at: datetime = Field(default_factory=_now)
    decided_at: datetime | None = None


class Milestone(BaseModel):
    """One concrete thing that must happen for a company to reach its next
    stage. This is how JARVIS runs a company that has no metrics yet: a
    pre-launch business is a list of things to ship and validate, each owned
    by a business agent, not a revenue dashboard."""

    id: str = Field(default_factory=_uuid)
    company_id: str
    title: str
    detail: str = ""
    stage_target: str = Field(default="launched", description="Stage this unlocks")
    owner_agent: str = "Chief of Staff"
    status: Literal["todo", "in_progress", "done", "blocked"] = "todo"
    blocker: str = Field(default="", description="Why it is stuck, if blocked")
    created_at: datetime = Field(default_factory=_now)
    completed_at: datetime | None = None


class PlannedMilestone(BaseModel):
    """A milestone as proposed by the Chief of Staff, before it is saved."""

    title: str
    detail: str = Field(..., description="What done looks like, concretely")
    owner_agent: str = Field(..., description="Which business agent drives it")


class LaunchPlan(BaseModel):
    """The Chief of Staff's plan to move a company to its next stage --
    what JARVIS produces instead of a briefing when there is no revenue to
    report yet."""

    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning_summary: str = ""
    current_stage_assessment: str = Field(..., description="Honest read of where the company is")
    critical_path: str = Field(..., description="The single fastest route to the next stage")
    milestones: list[PlannedMilestone] = Field(default_factory=list)


class PriorityItem(BaseModel):
    title: str
    why_now: str = Field(..., description="Why this matters today")
    owner_agent: str = Field(..., description="Which business agent should drive it")
    impact: Literal["high", "medium", "low"] = "medium"


class BusinessRisk(BaseModel):
    title: str
    severity: Literal["critical", "high", "medium", "low"] = "medium"
    mitigation: str = ""


class ExecutiveBriefing(BaseModel):
    """The Chief of Staff's morning briefing -- the centerpiece of the
    executive dashboard. Grounded in real company metric snapshots and
    pending approvals passed in as context, never invented."""

    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning_summary: str = ""
    headline: str = Field(..., description="One-line state of the business")
    business_health: Literal["strong", "stable", "warning", "critical"] = "stable"
    summary: str = Field(..., description="3-6 sentence executive summary")
    priorities: list[PriorityItem] = Field(default_factory=list)
    risks: list[BusinessRisk] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_now)


class ConversationTurn(BaseModel):
    """One prior exchange in the founder <-> JARVIS conversation, passed
    back with each /assistant call so replies stay contextual."""

    who: Literal["founder", "jarvis"]
    text: str


class AssistantReply(BaseModel):
    reply: str
    suggested_actions: list[str] = Field(default_factory=list)
