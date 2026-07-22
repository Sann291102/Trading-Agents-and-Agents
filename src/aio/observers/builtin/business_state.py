"""The pair of eyes that needs no credentials.

Everything else JARVIS watches is behind a key, a URL, or someone else's
uptime. This observer watches JARVIS's own database, which means it works on
a fresh clone with an empty `.env` -- it is what proves the whole
observe-then-act loop is real rather than a slot waiting for an integration.

What it looks for is deliberately not "anything unusual in the data". It is
the specific short list a competent chief of staff would raise unprompted:
work that is stuck, a decision the founder is sitting on, a company that has
earned its next stage, a company with no plan at all, numbers that have gone
stale, and cash running out. Each of those is a standing condition, so each
dedupe key is built from the row id it describes -- never from the moment it
was seen -- and the cycle collapses the repeats.

Stage discipline is enforced here, not left to judgement: a pre-revenue
company has no revenue, no burn worth extrapolating and no metrics to be
stale, so the money-shaped checks are skipped for it entirely. Reporting a
runway for a company that has never had a customer would be inventing a
number, which is the one thing JARVIS must never do.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from aio.models.business import Company, Milestone, next_stage
from aio.models.signals import Signal
from aio.observers.base import Observer, register_observer

if TYPE_CHECKING:
    from aio.business.service import BusinessService

# A blocker is normal for a day; a blocker nobody has touched for three is a
# project that has quietly stopped.
_BLOCKED_URGENT_AFTER = timedelta(days=3)

# Past this, the founder -- not the work -- is the bottleneck.
_APPROVAL_STALE_AFTER = timedelta(hours=24)

# A month without a number means the dashboard is describing a business that
# no longer exists.
_METRICS_STALE_AFTER = timedelta(days=30)

# Under a quarter of runway, raising or cutting has to start *now*, because
# both take longer than the cash lasts.
_RUNWAY_URGENT_MONTHS = 3.0


def _aware(moment: datetime) -> datetime:
    # SQLite drops tzinfo on round-trip; everything stored is UTC.
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment


def _humanize(delta: timedelta) -> str:
    hours = delta.total_seconds() / 3600
    if hours < 48:
        return f"{int(hours)}h"
    return f"{int(hours // 24)}d"


class BusinessStateObserver(Observer):
    """Watches JARVIS's own record of the business for things nobody typed in."""

    name = "business_state"
    display_name = "Business State"
    description = (
        "Watches milestones, approvals, stage progress and runway inside JARVIS's "
        "own records for problems and opportunities nobody reported."
    )
    watches = (
        "milestone_blocked",
        "approval_stale",
        "stage_ready_to_advance",
        "no_launch_plan",
        "metrics_stale",
        "runway_short",
    )

    def observe(self, business: "BusinessService") -> list[Signal]:
        now = datetime.now(timezone.utc)

        # How long each standing condition has already been reported, keyed by
        # dedupe key. Severity for "stuck" conditions is a function of
        # duration, and this is the only honest source of it: nothing on a
        # Milestone row records *when* it became blocked.
        first_seen = {
            signal.dedupe_key: _aware(signal.observed_at)
            for signal in business.list_signals(limit=500, open_only=True)
        }

        signals: list[Signal] = []
        for company in business.list_companies():
            milestones = business.list_milestones(company.id)
            signals.extend(self._milestone_signals(company, milestones, now, first_seen))
            signals.extend(self._plan_signals(company, milestones))
            if not company.is_pre_revenue:
                signals.extend(self._money_signals(business, company, now))
        signals.extend(self._approval_signals(business, now))
        return signals

    # -- work that is stuck ------------------------------------------------

    def _milestone_signals(
        self,
        company: Company,
        milestones: list[Milestone],
        now: datetime,
        first_seen: dict[str, datetime],
    ) -> list[Signal]:
        out: list[Signal] = []
        for milestone in milestones:
            if milestone.status != "blocked":
                continue
            key = f"milestone_blocked:{milestone.id}"
            stuck_for = now - first_seen.get(key, now)
            urgent = stuck_for >= _BLOCKED_URGENT_AFTER
            duration = f" Blocked for {_humanize(stuck_for)}." if urgent else ""
            out.append(
                Signal(
                    source=self.name,
                    kind="milestone_blocked",
                    title=f"{company.name}: '{milestone.title}' is blocked",
                    detail=(
                        f"{milestone.blocker or 'No blocker recorded.'} "
                        f"Owner: {milestone.owner_agent}.{duration}"
                    ).strip(),
                    severity="urgent" if urgent else "notable",
                    company_id=company.id,
                    dedupe_key=key,
                )
            )
        return out

    # -- the plan itself ---------------------------------------------------

    def _plan_signals(self, company: Company, milestones: list[Milestone]) -> list[Signal]:
        """The two opposite failures of a launch plan: there isn't one, or it
        is finished and nobody noticed."""
        out: list[Signal] = []

        if company.is_pre_revenue and not milestones:
            target = next_stage(company.stage) or "its next stage"
            out.append(
                Signal(
                    source=self.name,
                    kind="no_launch_plan",
                    title=f"{company.name} has no launch plan",
                    detail=(
                        f"Stage '{company.stage}' with zero milestones recorded. "
                        f"Nothing is defined as the path to '{target}', so no work "
                        f"can be prioritised or delegated."
                    ),
                    severity="notable",
                    company_id=company.id,
                    dedupe_key=f"no_launch_plan:{company.id}",
                )
            )
            return out

        target = next_stage(company.stage)
        if milestones and target and all(m.status == "done" for m in milestones):
            out.append(
                Signal(
                    source=self.name,
                    kind="stage_ready_to_advance",
                    title=f"{company.name} is ready to move to '{target}'",
                    detail=(
                        f"All {len(milestones)} milestone(s) for stage "
                        f"'{company.stage}' are done, but the stage has not moved. "
                        f"The plan is complete and the company is being run as if "
                        f"it were not."
                    ),
                    # High value and time-sensitive: the whole point of the
                    # stage ladder is that JARVIS behaves differently on the
                    # other side of it.
                    severity="urgent",
                    company_id=company.id,
                    # Stage is part of the identity: advancing ends this
                    # condition and any later plateau is a different one.
                    dedupe_key=f"stage_ready:{company.id}:{company.stage}",
                )
            )
        return out

    # -- the founder as bottleneck ----------------------------------------

    def _approval_signals(self, business: "BusinessService", now: datetime) -> list[Signal]:
        out: list[Signal] = []
        for approval in business.list_approvals(status="pending", limit=200):
            waiting = now - _aware(approval.created_at)
            if waiting < _APPROVAL_STALE_AFTER:
                continue
            blocked_work = (
                f" It is holding the action '{approval.pending_action}'."
                if approval.is_executable
                else ""
            )
            out.append(
                Signal(
                    source=self.name,
                    kind="approval_stale",
                    title=f"Approval waiting {_humanize(waiting)}: {approval.title}",
                    detail=(
                        f"Requested by {approval.requested_by} and still pending."
                        f"{blocked_work}"
                    ),
                    severity="notable",
                    company_id=approval.company_id,
                    dedupe_key=f"approval_stale:{approval.id}",
                )
            )
        return out

    # -- money (post-revenue only) ----------------------------------------

    def _money_signals(
        self, business: "BusinessService", company: Company, now: datetime
    ) -> list[Signal]:
        """Only ever called for a company past `building`. A pre-revenue
        company has no metrics to be stale and no burn to divide by, so these
        checks would be pure fabrication there."""
        out: list[Signal] = []
        latest = business.latest_metrics(company.id)

        if latest is None:
            out.append(
                Signal(
                    source=self.name,
                    kind="metrics_stale",
                    title=f"{company.name} has no metrics recorded",
                    detail=(
                        f"Stage '{company.stage}' means there are real numbers to "
                        f"report, but none have ever been recorded. Every briefing "
                        f"about this company is currently ungrounded."
                    ),
                    severity="notable",
                    company_id=company.id,
                    dedupe_key=f"metrics_stale:{company.id}",
                )
            )
            return out

        age = now - _aware(latest.recorded_at)
        if age >= _METRICS_STALE_AFTER:
            out.append(
                Signal(
                    source=self.name,
                    kind="metrics_stale",
                    title=f"{company.name} metrics are {_humanize(age)} old",
                    detail=(
                        f"Last snapshot {latest.recorded_at:%Y-%m-%d}. Decisions are "
                        f"being made on numbers older than a month."
                    ),
                    severity="notable",
                    company_id=company.id,
                    dedupe_key=f"metrics_stale:{company.id}",
                )
            )

        # Burn of zero is not "infinite runway", it is "nobody recorded the
        # burn" -- dividing by it would manufacture a crisis or hide one.
        if latest.burn_rate_monthly > 0:
            months = latest.cash_balance / latest.burn_rate_monthly
            if months < _RUNWAY_URGENT_MONTHS:
                out.append(
                    Signal(
                        source=self.name,
                        kind="runway_short",
                        title=f"{company.name} has {months:.1f} months of runway",
                        detail=(
                            f"Cash ${latest.cash_balance:,.0f} against burn "
                            f"${latest.burn_rate_monthly:,.0f}/mo. Raising or cutting "
                            f"takes longer than that."
                        ),
                        severity="urgent",
                        company_id=company.id,
                        dedupe_key=f"runway_short:{company.id}",
                    )
                )
        return out


register_observer(BusinessStateObserver())
