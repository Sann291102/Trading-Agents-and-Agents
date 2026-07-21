"""Running the company: the numbers, the plan, the stage, the questions.

Every action here is SAFE. Each one writes only to JARVIS's own database,
lands in the activity feed, and can be corrected by writing again -- so
routing them through an approval would add friction without buying any
safety. The irreversible, outward-facing work (mail, spend, publishing)
is what SENSITIVE is for.

Handlers resolve a company by *name*, never by id: the founder says
"TradeW", and so does the planner, which only ever sees the plain-text
business snapshot. A name that does not match is a user-input problem, not
a crash -- it comes back as a FAILED result naming the companies that do
exist, so the next attempt can be right.
"""

from __future__ import annotations

import difflib

from pydantic import BaseModel, Field

from aio.actions.base import ActionContext, ActionOutcome, ActionResult, ActionRisk
from aio.actions.registry import action
from aio.agents.business import BUSINESS_AGENT_CLASSES
from aio.business.service import BusinessService
from aio.models.business import (
    COMPANY_STAGES,
    Approval,
    BusinessMetricSnapshot,
    Company,
    Milestone,
)

MILESTONE_STATUSES = ("todo", "in_progress", "done", "blocked")

# Carried forward from the previous snapshot when the founder does not
# restate them -- see `record_company_metrics`.
_METRIC_FIELDS = (
    "mrr",
    "revenue_this_month",
    "customers",
    "new_customers_this_month",
    "churned_customers_this_month",
    "active_users",
    "support_open_tickets",
    "marketing_spend_this_month",
    "sales_pipeline_value",
    "cash_balance",
    "burn_rate_monthly",
)


def _failed(summary: str, detail: str = "") -> ActionResult:
    return ActionResult(outcome=ActionOutcome.FAILED, summary=summary, detail=detail)


def resolve_company(business: BusinessService, name: str) -> Company | None:
    """Find a company by name, case- and whitespace-insensitively, falling
    back to a prefix match so "tradew" and "TradeW " both land."""
    wanted = (name or "").strip().lower()
    if not wanted:
        return None
    companies = business.list_companies()
    for company in companies:
        if company.name.strip().lower() == wanted:
            return company
    for company in companies:
        if company.name.strip().lower().startswith(wanted):
            return company
    return None


def unknown_company(business: BusinessService, name: str) -> ActionResult:
    known = ", ".join(c.name for c in business.list_companies()) or "none yet"
    return _failed(
        f"Could not find a company called {name!r}",
        f"Connected companies: {known}. Use one of those names exactly.",
    )


def resolve_agent_role(role: str) -> str | None:
    """Canonical roster spelling of `role`, or None if no such agent exists.

    Owner names have to be real: a milestone owned by an invented "Product
    Agent" can never actually be delegated to anyone.
    """
    wanted = (role or "").strip().lower()
    for cls in BUSINESS_AGENT_CLASSES:
        if cls.role.lower() == wanted:
            return cls.role
    return None


def roster_names() -> str:
    return ", ".join(cls.role for cls in BUSINESS_AGENT_CLASSES)


# -- record_company_metrics --------------------------------------------------


class RecordCompanyMetricsParams(BaseModel):
    company_name: str = Field(..., description="Company these numbers belong to, e.g. 'TradeW'")
    mrr: float | None = Field(None, description="Monthly recurring revenue, in currency units")
    revenue_this_month: float | None = Field(None, description="Total revenue booked this month")
    customers: int | None = Field(None, description="Total paying customers right now")
    new_customers_this_month: int | None = Field(None, description="Customers won this month")
    churned_customers_this_month: int | None = Field(None, description="Customers lost this month")
    active_users: int | None = Field(None, description="Users active in the current period")
    support_open_tickets: int | None = Field(None, description="Support tickets currently open")
    marketing_spend_this_month: float | None = Field(None, description="Marketing spend this month")
    sales_pipeline_value: float | None = Field(None, description="Total value of the open pipeline")
    cash_balance: float | None = Field(None, description="Cash in the bank right now")
    burn_rate_monthly: float | None = Field(None, description="Net cash burned per month")
    notes: str = Field("", description="Anything about this snapshot worth remembering")


@action(
    "record_company_metrics",
    description="Record a snapshot of a company's numbers from figures the founder stated",
    risk=ActionRisk.SAFE,
    params_model=RecordCompanyMetricsParams,
    owner_agent="Business Analyst",
)
def record_company_metrics(
    context: ActionContext, params: RecordCompanyMetricsParams
) -> ActionResult:
    company = resolve_company(context.business, params.company_name)
    if company is None:
        return unknown_company(context.business, params.company_name)

    stated = {
        field: value
        for field in _METRIC_FIELDS
        if (value := getattr(params, field)) is not None
    }
    if not stated:
        return _failed(
            f"No numbers to record for {company.name}",
            "At least one metric (mrr, customers, cash_balance, ...) must be given.",
        )

    # Unstated fields carry forward from the last snapshot rather than
    # defaulting to zero: a founder saying "we're at 40 customers" must not
    # silently wipe the cash balance recorded last week.
    previous = context.business.latest_metrics(company.id)
    values = {field: getattr(previous, field) for field in _METRIC_FIELDS} if previous else {}
    values.update(stated)

    snapshot = context.business.record_metrics(
        BusinessMetricSnapshot(company_id=company.id, notes=params.notes, **values)
    )
    stated_text = ", ".join(f"{field}={value}" for field, value in stated.items())
    return ActionResult(
        outcome=ActionOutcome.EXECUTED,
        summary=f"Recorded {company.name} metrics: {stated_text}",
        detail=(
            f"Snapshot {snapshot.id} saved for {company.name}."
            + (" Unstated figures carried forward from the previous snapshot." if previous else "")
        ),
        data={"company_id": company.id, "snapshot_id": snapshot.id, "recorded": stated},
    )


# -- add_milestone -----------------------------------------------------------


class AddMilestoneParams(BaseModel):
    company_name: str = Field(..., description="Company whose plan this milestone belongs to")
    title: str = Field(..., description="Short name of the milestone, concrete enough to verify")
    detail: str = Field("", description="What 'done' looks like, concretely")
    owner_agent: str = Field(
        "Chief of Staff",
        description="Business agent who drives it -- must be an existing role, verbatim",
    )
    stage_target: str = Field("", description="Stage this unlocks; defaults to the next stage")


@action(
    "add_milestone",
    description="Add one milestone to a company's launch plan",
    risk=ActionRisk.SAFE,
    params_model=AddMilestoneParams,
    owner_agent="Chief of Staff",
)
def add_milestone(context: ActionContext, params: AddMilestoneParams) -> ActionResult:
    company = resolve_company(context.business, params.company_name)
    if company is None:
        return unknown_company(context.business, params.company_name)

    owner = resolve_agent_role(params.owner_agent)
    if owner is None:
        return _failed(
            f"No agent called {params.owner_agent!r} to own that milestone",
            f"Pick an owner from the roster: {roster_names()}.",
        )

    title = params.title.strip()
    if not title:
        return _failed(f"Milestone for {company.name} needs a title")

    from aio.models.business import next_stage

    milestone = context.business.create_milestone(
        Milestone(
            company_id=company.id,
            title=title,
            detail=params.detail,
            owner_agent=owner,
            stage_target=params.stage_target.strip() or next_stage(company.stage) or company.stage,
        )
    )
    return ActionResult(
        outcome=ActionOutcome.EXECUTED,
        summary=f"Added milestone '{title}' to {company.name}, owned by {owner}",
        detail=params.detail,
        data={"company_id": company.id, "milestone_id": milestone.id, "owner_agent": owner},
    )


# -- set_milestone_status ----------------------------------------------------


class SetMilestoneStatusParams(BaseModel):
    company_name: str = Field(..., description="Company the milestone belongs to")
    milestone_title: str = Field(..., description="Title of the milestone (approximate is fine)")
    status: str = Field(..., description="One of: todo, in_progress, done, blocked")
    blocker: str = Field("", description="Why it is stuck -- only used when status is 'blocked'")


@action(
    "set_milestone_status",
    description="Move a milestone to todo, in_progress, done or blocked",
    risk=ActionRisk.SAFE,
    params_model=SetMilestoneStatusParams,
    owner_agent="Chief of Staff",
)
def set_milestone_status(context: ActionContext, params: SetMilestoneStatusParams) -> ActionResult:
    company = resolve_company(context.business, params.company_name)
    if company is None:
        return unknown_company(context.business, params.company_name)

    status = params.status.strip().lower().replace(" ", "_").replace("-", "_")
    if status not in MILESTONE_STATUSES:
        return _failed(
            f"{params.status!r} is not a milestone status",
            f"Valid statuses: {', '.join(MILESTONE_STATUSES)}.",
        )

    milestones = context.business.list_milestones(company.id)
    if not milestones:
        return _failed(
            f"{company.name} has no milestones yet",
            "Plan the company's milestones before moving one.",
        )

    match = _match_milestone(milestones, params.milestone_title)
    if match is None:
        titles = "; ".join(m.title for m in milestones)
        return _failed(
            f"No milestone on {company.name} matching {params.milestone_title!r}",
            f"Current milestones: {titles}.",
        )

    updated = context.business.set_milestone_status(match.id, status, blocker=params.blocker)
    if updated is None:  # pragma: no cover - only if the row vanished mid-call
        return _failed(f"Milestone '{match.title}' disappeared before it could be updated")

    blocked_note = f" (blocked: {params.blocker})" if status == "blocked" and params.blocker else ""
    return ActionResult(
        outcome=ActionOutcome.EXECUTED,
        summary=f"Moved '{updated.title}' to {status} on {company.name}{blocked_note}",
        detail=updated.detail,
        data={"company_id": company.id, "milestone_id": updated.id, "status": status},
    )


def _match_milestone(milestones: list[Milestone], wanted: str) -> Milestone | None:
    """Exact title, then substring, then closest spelling.

    The title arrives from speech or from an LLM paraphrasing the plan, so
    insisting on a character-perfect match would make this action fail on
    almost every real call.
    """
    target = (wanted or "").strip().lower()
    if not target:
        return None
    by_title = {m.title.strip().lower(): m for m in milestones}
    if target in by_title:
        return by_title[target]
    contained = [m for m in milestones if target in m.title.strip().lower()]
    if len(contained) == 1:
        return contained[0]
    close = difflib.get_close_matches(target, list(by_title), n=1, cutoff=0.6)
    return by_title[close[0]] if close else (contained[0] if contained else None)


# -- update_company_stage ----------------------------------------------------


class UpdateCompanyStageParams(BaseModel):
    company_name: str = Field(..., description="Company to move along the lifecycle")
    stage: str = Field(
        ...,
        description=f"New stage, one of: {', '.join(COMPANY_STAGES)}",
    )


@action(
    "update_company_stage",
    description="Move a company to a new lifecycle stage (idea -> building -> launched -> ...)",
    risk=ActionRisk.SAFE,
    params_model=UpdateCompanyStageParams,
    owner_agent="Chief of Staff",
)
def update_company_stage(context: ActionContext, params: UpdateCompanyStageParams) -> ActionResult:
    company = resolve_company(context.business, params.company_name)
    if company is None:
        return unknown_company(context.business, params.company_name)

    stage = params.stage.strip().lower()
    if stage not in COMPANY_STAGES:
        return _failed(
            f"{params.stage!r} is not a company stage",
            f"Valid stages, in order: {', '.join(COMPANY_STAGES)}.",
        )
    if stage == company.stage:
        return ActionResult(
            outcome=ActionOutcome.EXECUTED,
            summary=f"{company.name} was already at the '{stage}' stage",
            data={"company_id": company.id, "stage": stage},
        )

    if not _persist_stage(context.business, company.id, stage):
        return _failed(
            f"Could not move {company.name} to '{stage}'",
            "The company record could not be updated.",
        )

    # Crossing into 'launched' is the moment briefings switch from milestones
    # to metrics, so it is worth calling out rather than logging silently.
    return ActionResult(
        outcome=ActionOutcome.EXECUTED,
        summary=f"Moved {company.name} from '{company.stage}' to '{stage}'",
        detail=(
            "Reporting now runs on metrics rather than milestones."
            if stage not in ("idea", "building")
            else "Reporting stays on milestones until launch."
        ),
        data={"company_id": company.id, "stage": stage, "previous_stage": company.stage},
    )


def _persist_stage(business: BusinessService, company_id: str, stage: str) -> bool:
    """Write a company's new stage.

    BusinessService exposes no company setter yet, so this prefers one if it
    ever appears and otherwise writes through the service's *own* session
    factory. Opening a second engine here instead would risk pointing at a
    different database than the rest of the run (tests and the API both hand
    BusinessService an explicit URL).
    """
    setter = getattr(business, "set_company_stage", None)
    if callable(setter):
        return setter(company_id, stage) is not None

    from aio.db.models import CompanyRecord

    session_factory = getattr(business, "_Session", None)
    if session_factory is None:  # pragma: no cover - defensive
        return False
    with session_factory() as session:
        record = session.get(CompanyRecord, company_id)
        if record is None:
            return False
        record.stage = stage
        session.commit()
    return True


# -- raise_approval ----------------------------------------------------------


class RaiseApprovalParams(BaseModel):
    title: str = Field(..., description="The decision, phrased as one line the founder can answer")
    detail: str = Field("", description="Context, options, and JARVIS's recommendation")
    company_name: str = Field("", description="Company this concerns, if any")


@action(
    "raise_approval",
    description="Park a decision for the founder to make",
    risk=ActionRisk.SAFE,
    params_model=RaiseApprovalParams,
    owner_agent="Chief of Staff",
)
def raise_approval(context: ActionContext, params: RaiseApprovalParams) -> ActionResult:
    """Creating an approval is itself safe -- it asks a question, it does not
    perform anything. Note this deliberately makes a *plain* approval with no
    pending action: approving it records the founder's answer rather than
    executing work, which is the difference between JARVIS asking and JARVIS
    proposing."""
    title = params.title.strip()
    if not title:
        return _failed("An approval needs a title the founder can answer")

    company = resolve_company(context.business, params.company_name) if params.company_name else None
    if params.company_name and company is None:
        return unknown_company(context.business, params.company_name)

    approval = context.business.create_approval(
        Approval(
            company_id=company.id if company else None,
            title=title,
            detail=params.detail,
            requested_by=context.actor,
        )
    )
    scope = f" for {company.name}" if company else ""
    return ActionResult(
        outcome=ActionOutcome.EXECUTED,
        summary=f"Raised a decision{scope}: {title}",
        detail=params.detail,
        data={"approval_id": approval.id, "company_id": approval.company_id},
    )
