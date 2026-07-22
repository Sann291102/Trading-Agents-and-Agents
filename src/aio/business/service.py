"""Company / metrics / approvals storage for the Executive Business OS.

Mirrors MemoryService's constructor pattern: its own SQLAlchemy engine
against the same shared Base/database. Seeds TradeW as the first connected
company on init so the executive dashboard is never empty.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from aio.config import settings
import json

from aio.db.models import (
    ActionRunRecord,
    ApprovalRecord,
    Base,
    BusinessMetricRecord,
    CompanyRecord,
    ConversationTurnRecord,
    MilestoneRecord,
    SignalRecord,
)
from aio.models.signals import Signal
from aio.models.business import (
    ActionRun,
    Approval,
    BusinessMetricSnapshot,
    Company,
    ConversationTurn,
    Milestone,
    next_stage,
)

_TRADEW_SEED = Company(
    name="TradeW",
    description=(
        "Trading platform for the Indian stock market, with its own product AI "
        "(Sentinel) for customers. Not launched yet -- JARVIS's job is to get it "
        "built, launched, and to its first paying customers."
    ),
    industry="Fintech / Capital Markets",
    stage="building",
    website="",
)


def _utc(dt: datetime) -> datetime:
    # SQLite drops tzinfo on round-trip; everything written is UTC.
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


class BusinessService:
    def __init__(self, database_url: str | None = None) -> None:
        self._engine = create_engine(database_url or settings.database_url, future=True)
        self._Session: sessionmaker[Session] = sessionmaker(bind=self._engine, future=True)

    def init_schema(self) -> None:
        Base.metadata.create_all(self._engine)
        self._migrate_added_columns()
        self._seed()

    def _migrate_added_columns(self) -> None:
        """`create_all` only creates tables that do not exist yet -- it never
        alters an existing table, so a column added to a model after the
        database was first created (like `Approval.pending_action`) is
        silently absent until this runs. There is no formal migration system
        in this vertical slice, and the sqlite dev database is checked into
        git as local runtime state, so every table that predates a model
        change needs its own catch-up here rather than crashing the first
        query that touches the new column."""
        inspector = inspect(self._engine)
        if "approvals" not in inspector.get_table_names():
            return  # a fresh create_all() above already has every column
        existing = {col["name"] for col in inspector.get_columns("approvals")}
        with self._engine.begin() as conn:
            if "pending_action" not in existing:
                conn.execute(text("ALTER TABLE approvals ADD COLUMN pending_action VARCHAR DEFAULT ''"))
            if "pending_params_json" not in existing:
                conn.execute(text("ALTER TABLE approvals ADD COLUMN pending_params_json TEXT DEFAULT ''"))

    def _seed(self) -> None:
        with self._Session() as session:
            exists = session.scalar(
                select(CompanyRecord).where(CompanyRecord.name == _TRADEW_SEED.name)
            )
            if exists is None:
                session.add(_company_record(_TRADEW_SEED))
                session.commit()

    # -- companies --------------------------------------------------------

    def create_company(self, company: Company) -> Company:
        with self._Session() as session:
            record = _company_record(company)
            session.add(record)
            session.commit()
            session.refresh(record)
            return _to_company(record)

    def list_companies(self) -> list[Company]:
        with self._Session() as session:
            stmt = select(CompanyRecord).order_by(CompanyRecord.created_at.asc())
            return [_to_company(r) for r in session.scalars(stmt)]

    def get_company(self, company_id: str) -> Company | None:
        with self._Session() as session:
            record = session.get(CompanyRecord, company_id)
            return _to_company(record) if record is not None else None

    # -- metrics ----------------------------------------------------------

    def record_metrics(self, snapshot: BusinessMetricSnapshot) -> BusinessMetricSnapshot:
        with self._Session() as session:
            record = BusinessMetricRecord(**snapshot.model_dump())
            session.add(record)
            session.commit()
            session.refresh(record)
            return _to_snapshot(record)

    def list_metrics(self, company_id: str, limit: int = 12) -> list[BusinessMetricSnapshot]:
        """Most recent first -- [0] is the current state of the business."""
        with self._Session() as session:
            stmt = (
                select(BusinessMetricRecord)
                .where(BusinessMetricRecord.company_id == company_id)
                .order_by(BusinessMetricRecord.recorded_at.desc())
                .limit(limit)
            )
            return [_to_snapshot(r) for r in session.scalars(stmt)]

    def latest_metrics(self, company_id: str) -> BusinessMetricSnapshot | None:
        rows = self.list_metrics(company_id, limit=1)
        return rows[0] if rows else None

    # -- approvals --------------------------------------------------------

    def create_approval(self, approval: Approval) -> Approval:
        with self._Session() as session:
            record = ApprovalRecord(**approval.model_dump())
            session.add(record)
            session.commit()
            session.refresh(record)
            return _to_approval(record)

    def list_approvals(self, status: str | None = "pending", limit: int = 50) -> list[Approval]:
        with self._Session() as session:
            stmt = select(ApprovalRecord).order_by(ApprovalRecord.created_at.desc()).limit(limit)
            if status:
                stmt = stmt.where(ApprovalRecord.status == status)
            return [_to_approval(r) for r in session.scalars(stmt)]

    def get_approval(self, approval_id: str) -> Approval | None:
        with self._Session() as session:
            record = session.get(ApprovalRecord, approval_id)
            return _to_approval(record) if record is not None else None

    def decide_approval(self, approval_id: str, decision: str) -> Approval | None:
        if decision not in ("approved", "rejected"):
            raise ValueError(f"invalid decision {decision!r}")
        with self._Session() as session:
            record = session.get(ApprovalRecord, approval_id)
            if record is None:
                return None
            record.status = decision
            record.decided_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(record)
            return _to_approval(record)

    # -- signals (what JARVIS noticed on its own) -------------------------

    def record_signal(self, signal: Signal) -> Signal:
        """Persist an observation, collapsing repeats of a standing condition.

        An observer re-reports the same fact every cycle by design (the site
        is *still* down), so an unresolved signal with the same dedupe_key is
        updated rather than duplicated. The returned signal's `times_seen`
        tells the caller whether this was new (1) or a repeat.
        """
        with self._Session() as session:
            existing = session.scalar(
                select(SignalRecord)
                .where(SignalRecord.dedupe_key == signal.dedupe_key)
                .where(SignalRecord.resolved_at.is_(None))
                .order_by(SignalRecord.observed_at.desc())
            )
            if existing is not None:
                existing.times_seen += 1
                existing.last_seen_at = datetime.now(timezone.utc)
                # Refresh the wording -- a condition can worsen between
                # observations (3 tickets open becomes 30).
                existing.title = signal.title
                existing.detail = signal.detail
                existing.severity = signal.severity
                session.commit()
                session.refresh(existing)
                return _to_signal(existing)

            record = SignalRecord(**signal.model_dump())
            session.add(record)
            session.commit()
            session.refresh(record)
            return _to_signal(record)

    def list_signals(
        self, *, limit: int = 50, open_only: bool = False, unprocessed_only: bool = False
    ) -> list[Signal]:
        """Newest first."""
        with self._Session() as session:
            stmt = select(SignalRecord)
            if open_only:
                stmt = stmt.where(SignalRecord.resolved_at.is_(None))
            if unprocessed_only:
                stmt = stmt.where(SignalRecord.processed_at.is_(None))
            stmt = stmt.order_by(SignalRecord.last_seen_at.desc(), SignalRecord.id).limit(limit)
            return [_to_signal(r) for r in session.scalars(stmt)]

    def mark_signals_processed(self, signal_ids: list[str]) -> int:
        """Take signals out of the executive loop's inbox once it has taken
        them into account, so the next cycle reasons about what is new."""
        if not signal_ids:
            return 0
        with self._Session() as session:
            now = datetime.now(timezone.utc)
            count = 0
            for signal_id in signal_ids:
                record = session.get(SignalRecord, signal_id)
                if record is not None and record.processed_at is None:
                    record.processed_at = now
                    count += 1
            session.commit()
            return count

    def resolve_signals_absent_from(self, source: str, seen_keys: set[str]) -> int:
        """Close conditions this observer no longer reports.

        Without this a signal would be true forever: the site comes back up,
        but "website offline" stays open and keeps driving the loop. An
        observer's output is the complete current truth for its own source,
        so anything it stops mentioning has ended.
        """
        with self._Session() as session:
            stmt = (
                select(SignalRecord)
                .where(SignalRecord.source == source)
                .where(SignalRecord.resolved_at.is_(None))
            )
            now = datetime.now(timezone.utc)
            count = 0
            for record in session.scalars(stmt):
                if record.dedupe_key not in seen_keys:
                    record.resolved_at = now
                    count += 1
            session.commit()
            return count

    def signal_inbox(self, limit: int = 15) -> str:
        """Open, unprocessed observations as planner context -- the Observe
        stage of the autonomous loop. Urgent first, then most-repeated, since
        a condition seen many times has been ignored many times."""
        signals = self.list_signals(limit=100, open_only=True, unprocessed_only=True)
        if not signals:
            return "Nothing new observed."
        rank = {"urgent": 0, "notable": 1, "info": 2}
        signals.sort(key=lambda s: (rank.get(s.severity, 3), -s.times_seen))
        return "\n".join(f"  {s.as_prompt_line()}" for s in signals[:limit])

    # -- action audit trail -----------------------------------------------

    def record_action_run(
        self,
        *,
        action: str,
        actor: str,
        params: dict,
        outcome: str,
        summary: str,
        detail: str = "",
    ) -> ActionRun:
        run = ActionRun(
            action=action,
            actor=actor,
            params_json=json.dumps(params, default=str),
            outcome=outcome,
            summary=summary,
            detail=detail,
        )
        with self._Session() as session:
            record = ActionRunRecord(**run.model_dump())
            session.add(record)
            session.commit()
            session.refresh(record)
            return _to_action_run(record)

    def list_action_runs(self, limit: int = 50) -> list[ActionRun]:
        """Newest first -- what JARVIS has been doing, for the activity feed."""
        with self._Session() as session:
            stmt = (
                select(ActionRunRecord)
                .order_by(ActionRunRecord.created_at.desc(), ActionRunRecord.id)
                .limit(limit)
            )
            return [_to_action_run(r) for r in session.scalars(stmt)]

    def recent_action_summary(self, limit: int = 12) -> str:
        """What JARVIS already did recently, as planner context. Without this
        the autonomous loop has no memory of its own work and re-proposes the
        same action every cycle."""
        runs = self.list_action_runs(limit=limit)
        if not runs:
            return "No actions taken yet."
        return "\n".join(
            f"  [{run.created_at:%Y-%m-%d %H:%M}] {run.action} -> {run.outcome}: {run.summary}"
            for run in reversed(runs)
        )

    # -- milestones (how a pre-revenue company is run) --------------------

    def create_milestone(self, milestone: Milestone) -> Milestone:
        with self._Session() as session:
            record = MilestoneRecord(**milestone.model_dump())
            session.add(record)
            session.commit()
            session.refresh(record)
            return _to_milestone(record)

    def list_milestones(self, company_id: str) -> list[Milestone]:
        """Oldest first -- the order the Chief of Staff planned them, which
        is the order they should be worked."""
        with self._Session() as session:
            stmt = (
                select(MilestoneRecord)
                .where(MilestoneRecord.company_id == company_id)
                .order_by(MilestoneRecord.created_at.asc())
            )
            return [_to_milestone(r) for r in session.scalars(stmt)]

    def set_milestone_status(
        self, milestone_id: str, status: str, blocker: str = ""
    ) -> Milestone | None:
        if status not in ("todo", "in_progress", "done", "blocked"):
            raise ValueError(f"invalid milestone status {status!r}")
        with self._Session() as session:
            record = session.get(MilestoneRecord, milestone_id)
            if record is None:
                return None
            record.status = status
            record.blocker = blocker if status == "blocked" else ""
            record.completed_at = datetime.now(timezone.utc) if status == "done" else None
            session.commit()
            session.refresh(record)
            return _to_milestone(record)

    def replace_milestones(self, company_id: str, milestones: list[Milestone]) -> list[Milestone]:
        """Swap in a freshly generated launch plan, keeping any milestone
        already done or in progress -- regenerating a plan must never erase
        work the founder has already banked."""
        kept = [m for m in self.list_milestones(company_id) if m.status in ("done", "in_progress")]
        kept_titles = {m.title.strip().lower() for m in kept}
        with self._Session() as session:
            stmt = select(MilestoneRecord).where(MilestoneRecord.company_id == company_id)
            for record in session.scalars(stmt):
                if record.status not in ("done", "in_progress"):
                    session.delete(record)
            session.commit()
        for milestone in milestones:
            if milestone.title.strip().lower() not in kept_titles:
                self.create_milestone(milestone)
        return self.list_milestones(company_id)

    # -- conversation memory ----------------------------------------------

    def save_turn(self, turn: ConversationTurn) -> None:
        with self._Session() as session:
            session.add(ConversationTurnRecord(who=turn.who, text=turn.text))
            session.commit()

    def recent_turns(self, limit: int = 30) -> list[ConversationTurn]:
        """Chronological (oldest first) tail of the founder <-> JARVIS
        conversation -- ready to hand to the assistant as history or to the
        frontend as the restored transcript."""
        with self._Session() as session:
            stmt = (
                select(ConversationTurnRecord)
                .order_by(ConversationTurnRecord.created_at.desc(), ConversationTurnRecord.id)
                .limit(limit)
            )
            rows = list(session.scalars(stmt))
        return [ConversationTurn(who=r.who, text=r.text) for r in reversed(rows)]

    # -- briefing context -------------------------------------------------

    def snapshot_for_briefing(self) -> str:
        """A plain-text digest of every company's real state + pending
        approvals -- the grounding context handed to the Chief of Staff and
        the Executive Assistant so their output is about real data, never
        invented.

        What "state" means depends on the stage. A pre-revenue company has no
        customers or MRR, so reporting on metrics there would be fiction: it
        is described by its milestones and what is blocking the next stage
        instead. Saying so explicitly is what stops the model from filling
        the silence with plausible-sounding numbers.
        """
        lines: list[str] = []
        for company in self.list_companies():
            lines.append(f"Company: {company.name} ({company.stage}) -- {company.description}")
            target = next_stage(company.stage)

            if company.is_pre_revenue:
                lines.append(
                    f"  PRE-REVENUE: not launched yet. No customers, no revenue, no MRR -- "
                    f"these do not exist yet and must never be reported as numbers. "
                    f"The goal is reaching '{target}'."
                    if target
                    else "  PRE-REVENUE: not launched yet."
                )
                milestones = self.list_milestones(company.id)
                if not milestones:
                    lines.append(
                        "  No launch plan yet -- the first job is deciding what must ship."
                    )
                else:
                    lines.append("  Milestones on the path to launch:")
                    for milestone in milestones:
                        note = f" BLOCKED: {milestone.blocker}" if milestone.blocker else ""
                        lines.append(
                            f"    [{milestone.status}] {milestone.title} "
                            f"(owner: {milestone.owner_agent}){note}"
                        )
                continue

            history = self.list_metrics(company.id, limit=3)
            if not history:
                lines.append("  No metric snapshots recorded yet.")
            for snap in history:
                lines.append(
                    f"  [{snap.recorded_at:%Y-%m-%d}] MRR ${snap.mrr:,.0f} | "
                    f"revenue ${snap.revenue_this_month:,.0f} | {snap.customers} customers "
                    f"(+{snap.new_customers_this_month}/-{snap.churned_customers_this_month}) | "
                    f"{snap.active_users} active users | {snap.support_open_tickets} open tickets | "
                    f"pipeline ${snap.sales_pipeline_value:,.0f} | cash ${snap.cash_balance:,.0f} | "
                    f"burn ${snap.burn_rate_monthly:,.0f}/mo"
                    + (f" | notes: {snap.notes}" if snap.notes else "")
                )
        pending = self.list_approvals(status="pending")
        if pending:
            lines.append("Pending approvals:")
            lines.extend(f"  - {a.title} (requested by {a.requested_by})" for a in pending)
        return "\n".join(lines) or "No companies connected yet."


def _company_record(company: Company) -> CompanyRecord:
    return CompanyRecord(**company.model_dump())


def _to_company(record: CompanyRecord) -> Company:
    return Company(
        id=record.id,
        name=record.name,
        description=record.description,
        industry=record.industry,
        stage=record.stage,
        website=record.website,
        created_at=_utc(record.created_at),
    )


def _to_snapshot(record: BusinessMetricRecord) -> BusinessMetricSnapshot:
    return BusinessMetricSnapshot(
        id=record.id,
        company_id=record.company_id,
        mrr=record.mrr,
        revenue_this_month=record.revenue_this_month,
        customers=record.customers,
        new_customers_this_month=record.new_customers_this_month,
        churned_customers_this_month=record.churned_customers_this_month,
        active_users=record.active_users,
        support_open_tickets=record.support_open_tickets,
        marketing_spend_this_month=record.marketing_spend_this_month,
        sales_pipeline_value=record.sales_pipeline_value,
        cash_balance=record.cash_balance,
        burn_rate_monthly=record.burn_rate_monthly,
        notes=record.notes,
        recorded_at=_utc(record.recorded_at),
    )


def _to_milestone(record: MilestoneRecord) -> Milestone:
    return Milestone(
        id=record.id,
        company_id=record.company_id,
        title=record.title,
        detail=record.detail,
        stage_target=record.stage_target,
        owner_agent=record.owner_agent,
        status=record.status,
        blocker=record.blocker,
        created_at=_utc(record.created_at),
        completed_at=_utc(record.completed_at) if record.completed_at else None,
    )


def _to_approval(record: ApprovalRecord) -> Approval:
    return Approval(
        id=record.id,
        company_id=record.company_id,
        title=record.title,
        detail=record.detail,
        requested_by=record.requested_by,
        status=record.status,
        pending_action=record.pending_action,
        pending_params_json=record.pending_params_json,
        created_at=_utc(record.created_at),
        decided_at=_utc(record.decided_at) if record.decided_at else None,
    )


def _to_signal(record: SignalRecord) -> Signal:
    return Signal(
        id=record.id,
        source=record.source,
        kind=record.kind,
        title=record.title,
        detail=record.detail,
        severity=record.severity,
        company_id=record.company_id,
        dedupe_key=record.dedupe_key,
        times_seen=record.times_seen,
        observed_at=_utc(record.observed_at),
        last_seen_at=_utc(record.last_seen_at),
        processed_at=_utc(record.processed_at) if record.processed_at else None,
        resolved_at=_utc(record.resolved_at) if record.resolved_at else None,
    )


def _to_action_run(record: ActionRunRecord) -> ActionRun:
    return ActionRun(
        id=record.id,
        action=record.action,
        actor=record.actor,
        params_json=record.params_json,
        outcome=record.outcome,
        summary=record.summary,
        detail=record.detail,
        created_at=_utc(record.created_at),
    )
