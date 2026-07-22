"""Observer tests -- what JARVIS notices without being asked.

The load-bearing behaviour under test is not "does an observer produce a
signal" but what happens on the *second* pass: a standing condition must
collapse onto one signal, a fixed condition must resolve, and a broken
observer must resolve nothing. Those three are what make an unattended loop
survivable, and each has its own test below.
"""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from aio.business import BusinessService
from aio.models.business import Approval, BusinessMetricSnapshot, Company, Milestone
from aio.models.signals import Signal
from aio.observers import (
    Observer,
    all_observers,
    available_observers,
    get_observer,
    run_observation_cycle,
)
from aio.observers.builtin.business_state import BusinessStateObserver
from aio.observers.builtin.github import GitHubObserver
from aio.observers.builtin.web import WebsiteObserver


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture()
def service() -> BusinessService:
    svc = BusinessService(database_url="sqlite:///:memory:")
    svc.init_schema()
    return svc


@pytest.fixture()
def state() -> BusinessStateObserver:
    return BusinessStateObserver()


def _kinds(signals: list[Signal]) -> set[str]:
    return {s.kind for s in signals}


def _for_company(signals: list[Signal], company_id: str) -> list[Signal]:
    return [s for s in signals if s.company_id == company_id]


def _blocked_milestone(service: BusinessService, company_id: str) -> Milestone:
    milestone = service.create_milestone(
        Milestone(
            company_id=company_id,
            title="Get SEBI registration",
            owner_agent="Operations Director",
        )
    )
    return service.set_milestone_status(milestone.id, "blocked", "Waiting on regulator")


# -- registration ---------------------------------------------------------


def test_importing_the_package_registers_the_builtin_observers():
    names = {o.name for o in all_observers()}
    assert {"business_state", "website", "github"} <= names
    assert get_observer("business_state") is not None


def test_business_state_needs_no_configuration():
    """The one that must work on a fresh clone with an empty .env."""
    assert BusinessStateObserver().available() is True
    assert BusinessStateObserver().status().setup_hint == ""
    assert "business_state" in {o.name for o in available_observers()}


def test_github_is_unavailable_without_a_token_and_names_the_env_var(monkeypatch):
    # `Settings` has no github_token field, so the observer must fall back to
    # "off" rather than crash -- that degradation is the whole point of the
    # credentialed-observer template.
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    observer = GitHubObserver()
    status = observer.status()
    assert status.available is False
    assert "GITHUB_TOKEN" in status.setup_hint
    assert "GITHUB_REPO" in status.setup_hint
    # An unavailable observer never even runs.
    assert observer.safe_observe(None) is None


def test_github_turns_on_with_a_token_and_reads_the_repo(service, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("GITHUB_REPO", "tradew/platform")
    observer = GitHubObserver()
    assert observer.available() is True

    opened = (_now() - timedelta(days=9)).isoformat().replace("+00:00", "Z")
    recent = _now().isoformat().replace("+00:00", "Z")
    payload = [
        {"number": 7, "title": "Refactor order router", "created_at": opened,
         "html_url": "https://github.com/tradew/platform/pull/7", "pull_request": {}},
        {"number": 8, "title": "Fresh PR", "created_at": recent, "pull_request": {}},
    ] + [{"number": i, "title": f"issue {i}", "created_at": recent} for i in range(100, 112)]

    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kwargs: httpx.Response(200, json=payload, request=httpx.Request("GET", url)),
    )

    by_kind = {s.kind: s for s in observer.observe(service)}
    assert by_kind["github_pr_waiting"].dedupe_key == "github_pr:tradew/platform:7"
    assert by_kind["github_issues_open"].dedupe_key == "github_issues:tradew/platform"
    # The fresh PR is not yet a problem, and PRs are not counted as issues.
    assert "12 open issues" in by_kind["github_issues_open"].title


def test_github_api_failure_resolves_nothing(service, monkeypatch):
    """Returning [] would be a positive claim that every open PR just got
    merged. Failing loudly reaches safe_observe, which says 'no opinion'."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("GITHUB_REPO", "tradew/platform")
    observer = GitHubObserver()
    monkeypatch.setattr(
        httpx, "get", lambda url, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("no net"))
    )

    assert observer.safe_observe(service) is None


def test_every_observer_declares_what_it_watches():
    for observer in all_observers():
        status = observer.status()
        assert status.display_name and status.description
        assert status.watches, f"{status.name} claims to watch nothing"


# -- the core dedupe / resolve contract -----------------------------------


def test_blocked_milestone_raises_a_signal_with_a_stable_dedupe_key(service, state):
    company = service.list_companies()[0]
    milestone = _blocked_milestone(service, company.id)

    first = [s for s in state.observe(service) if s.kind == "milestone_blocked"]
    second = [s for s in state.observe(service) if s.kind == "milestone_blocked"]

    assert len(first) == 1
    assert first[0].dedupe_key == f"milestone_blocked:{milestone.id}"
    # Stable across passes and across the wording of the moment.
    assert first[0].dedupe_key == second[0].dedupe_key
    assert first[0].severity == "notable"
    assert "SEBI" in first[0].title
    assert "Waiting on regulator" in first[0].detail


def test_repeated_observation_collapses_onto_one_signal(service, state):
    """The single most important behaviour in the system: an observer
    re-reports the same standing condition every cycle by design, and the
    feed must show one signal seen twice, not two signals."""
    company = service.list_companies()[0]
    _blocked_milestone(service, company.id)

    first_cycle = run_observation_cycle(service, [state])
    second_cycle = run_observation_cycle(service, [state])

    assert "milestone_blocked" in _kinds(first_cycle)
    # Nothing changed, so nothing is new.
    assert second_cycle == []

    stored = [s for s in service.list_signals(limit=50) if s.kind == "milestone_blocked"]
    assert len(stored) == 1
    assert stored[0].times_seen == 2
    assert stored[0].is_open


def test_fixing_the_condition_resolves_the_signal(service, state):
    company = service.list_companies()[0]
    milestone = _blocked_milestone(service, company.id)
    run_observation_cycle(service, [state])

    service.set_milestone_status(milestone.id, "in_progress")
    run_observation_cycle(service, [state])

    stored = [s for s in service.list_signals(limit=50) if s.kind == "milestone_blocked"]
    assert len(stored) == 1
    assert stored[0].is_open is False
    assert stored[0].resolved_at is not None


def test_a_standing_blocker_escalates_to_urgent(service, state):
    """Duration is the only evidence that a blocker has become a stalled
    project, so severity has to be a function of how long JARVIS has been
    saying it."""
    company = service.list_companies()[0]
    milestone = _blocked_milestone(service, company.id)
    run_observation_cycle(service, [state])

    stored = next(s for s in service.list_signals(limit=50) if s.kind == "milestone_blocked")
    assert stored.severity == "notable"

    # Backdate the signal: the condition has been true for a week.
    _backdate_signal(service, stored.id, days=7)
    run_observation_cycle(service, [state])

    escalated = next(s for s in service.list_signals(limit=50) if s.kind == "milestone_blocked")
    assert escalated.id == stored.id
    assert escalated.dedupe_key == f"milestone_blocked:{milestone.id}"
    assert escalated.severity == "urgent"


def _backdate_signal(service: BusinessService, signal_id: str, *, days: int) -> None:
    from aio.db.models import SignalRecord

    with service._Session() as session:  # noqa: SLF001 -- no public backdating API
        record = session.get(SignalRecord, signal_id)
        record.observed_at = _now() - timedelta(days=days)
        session.commit()


# -- resilience -----------------------------------------------------------


class _FlakyObserver(Observer):
    """Reports one condition, then starts crashing."""

    name = "flaky_test_observer"
    display_name = "Flaky"
    description = "Fails on demand."
    watches = ("flaky_condition",)

    def __init__(self) -> None:
        self.explode = False

    def observe(self, business) -> list[Signal]:
        if self.explode:
            raise RuntimeError("token expired")
        return [
            Signal(
                source=self.name,
                kind="flaky_condition",
                title="Something is wrong out there",
                severity="urgent",
                dedupe_key="flaky:1",
            )
        ]


def test_a_crashing_observer_neither_breaks_the_cycle_nor_resolves_its_signals(service, state):
    """A failed observer has no opinion about what is still true. Silently
    closing real problems because a credential expired would be the worst
    possible failure mode."""
    company = service.list_companies()[0]
    _blocked_milestone(service, company.id)
    flaky = _FlakyObserver()

    run_observation_cycle(service, [flaky, state])
    assert any(s.kind == "flaky_condition" and s.is_open for s in service.list_signals(limit=50))

    flaky.explode = True
    fresh = run_observation_cycle(service, [flaky, state])

    # The healthy observer still ran in the same sweep.
    assert fresh == []
    stored = {s.kind: s for s in service.list_signals(limit=50)}
    assert stored["flaky_condition"].is_open is True
    assert stored["milestone_blocked"].is_open is True
    assert stored["milestone_blocked"].times_seen == 2


# -- stage discipline: never invent numbers for a pre-revenue company -----


def test_pre_revenue_company_never_gets_runway_or_stale_metrics_signals(service, state):
    """TradeW is pre-revenue. Even with alarming numbers attached, runway and
    metric-staleness are meaningless there -- reporting them would be
    fabricating a business that does not exist yet."""
    company = service.list_companies()[0]
    assert company.is_pre_revenue
    service.record_metrics(
        BusinessMetricSnapshot(
            company_id=company.id,
            cash_balance=1000.0,
            burn_rate_monthly=10000.0,  # 0.1 months if this were meaningful
            recorded_at=_now() - timedelta(days=90),
        )
    )

    kinds = _kinds(_for_company(state.observe(service), company.id))

    assert "runway_short" not in kinds
    assert "metrics_stale" not in kinds


def test_launched_company_does_get_runway_and_stale_metrics_signals(service, state):
    """The same data past the revenue line is a real emergency -- proof the
    rule above is stage discipline, not a dead code path."""
    company = service.create_company(Company(name="Launched Co", stage="operating"))
    service.record_metrics(
        BusinessMetricSnapshot(
            company_id=company.id,
            cash_balance=1000.0,
            burn_rate_monthly=10000.0,
            recorded_at=_now() - timedelta(days=90),
        )
    )

    signals = _for_company(state.observe(service), company.id)
    by_kind = {s.kind: s for s in signals}

    assert by_kind["runway_short"].severity == "urgent"
    assert "0.1 months" in by_kind["runway_short"].title
    assert by_kind["metrics_stale"].severity == "notable"


def test_zero_burn_never_produces_a_runway_signal(service, state):
    """Burn of zero means nobody recorded the burn, not infinite runway."""
    company = service.create_company(Company(name="No Burn Co", stage="operating"))
    service.record_metrics(
        BusinessMetricSnapshot(company_id=company.id, cash_balance=0.0, burn_rate_monthly=0.0)
    )

    assert "runway_short" not in _kinds(_for_company(state.observe(service), company.id))


def test_launched_company_with_no_metrics_at_all_is_flagged(service, state):
    company = service.create_company(Company(name="Silent Co", stage="launched"))

    signals = _for_company(state.observe(service), company.id)
    stale = next(s for s in signals if s.kind == "metrics_stale")
    assert stale.dedupe_key == f"metrics_stale:{company.id}"
    assert "no metrics" in stale.title.lower()


# -- the rest of the business_state checks --------------------------------


def test_pre_revenue_company_with_no_milestones_has_no_plan(service, state):
    company = service.list_companies()[0]

    signals = _for_company(state.observe(service), company.id)
    plan = next(s for s in signals if s.kind == "no_launch_plan")
    assert plan.severity == "notable"
    assert plan.dedupe_key == f"no_launch_plan:{company.id}"

    # Planning the work ends the condition.
    service.create_milestone(Milestone(company_id=company.id, title="Ship beta"))
    assert "no_launch_plan" not in _kinds(_for_company(state.observe(service), company.id))


def test_completed_plan_with_an_unchanged_stage_is_urgent(service, state):
    """The highest-value thing this observer does: the company earned its
    next stage and is still being run as if it had not."""
    company = service.list_companies()[0]
    for title in ("Build MVP", "Onboard first users"):
        milestone = service.create_milestone(Milestone(company_id=company.id, title=title))
        service.set_milestone_status(milestone.id, "done")

    signals = _for_company(state.observe(service), company.id)
    ready = next(s for s in signals if s.kind == "stage_ready_to_advance")
    assert ready.severity == "urgent"
    assert ready.dedupe_key == f"stage_ready:{company.id}:building"
    assert "launched" in ready.title


def test_unfinished_plan_is_not_reported_as_ready(service, state):
    company = service.list_companies()[0]
    done = service.create_milestone(Milestone(company_id=company.id, title="Build MVP"))
    service.set_milestone_status(done.id, "done")
    service.create_milestone(Milestone(company_id=company.id, title="Onboard first users"))

    assert "stage_ready_to_advance" not in _kinds(_for_company(state.observe(service), company.id))


def test_approval_pending_over_a_day_makes_the_founder_the_bottleneck(service, state):
    company = service.list_companies()[0]
    service.create_approval(
        Approval(
            company_id=company.id,
            title="Sign the broker agreement",
            requested_by="Operations Director",
            pending_action="raise_approval",
            created_at=_now() - timedelta(hours=30),
        )
    )
    fresh = service.create_approval(
        Approval(company_id=company.id, title="Just asked", created_at=_now())
    )

    signals = [s for s in state.observe(service) if s.kind == "approval_stale"]
    assert len(signals) == 1
    assert "Sign the broker agreement" in signals[0].title
    assert signals[0].severity == "notable"
    assert fresh.id not in signals[0].dedupe_key


def test_deciding_an_approval_resolves_its_signal(service, state):
    company = service.list_companies()[0]
    approval = service.create_approval(
        Approval(company_id=company.id, title="Old decision", created_at=_now() - timedelta(days=2))
    )
    run_observation_cycle(service, [state])

    service.decide_approval(approval.id, "approved")
    run_observation_cycle(service, [state])

    stale = next(s for s in service.list_signals(limit=50) if s.kind == "approval_stale")
    assert stale.is_open is False


def test_signals_reach_the_planner_inbox(service, state):
    """Observing is only useful if the reasoning half can read it."""
    company = service.list_companies()[0]
    _blocked_milestone(service, company.id)
    run_observation_cycle(service, [state])

    inbox = service.signal_inbox()
    assert "milestone_blocked" in inbox

    service.mark_signals_processed([s.id for s in service.list_signals(limit=50)])
    assert service.signal_inbox() == "Nothing new observed."


# -- website --------------------------------------------------------------


def test_company_with_no_website_is_never_reported(service, monkeypatch):
    """Most pre-launch companies have no site. That is not an outage, and the
    observer must not even make a request."""

    def _fail(*args, **kwargs):
        raise AssertionError("no HTTP request should be made")

    monkeypatch.setattr(httpx, "get", _fail)
    assert service.list_companies()[0].website == ""

    assert WebsiteObserver().observe(service) == []


def test_unreachable_website_is_urgent(service, monkeypatch):
    company = service.create_company(Company(name="Downed Co", website="downed.example"))

    def _refused(url, **kwargs):
        assert url == "https://downed.example"  # bare domains get a scheme
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", _refused)

    signals = _for_company(WebsiteObserver().observe(service), company.id)
    assert len(signals) == 1
    assert signals[0].kind == "website_offline"
    assert signals[0].severity == "urgent"
    assert signals[0].dedupe_key == f"website_offline:{company.id}"


def test_server_error_counts_as_offline(service, monkeypatch):
    company = service.create_company(Company(name="Erroring Co", website="https://err.example"))
    monkeypatch.setattr(
        httpx, "get", lambda url, **kwargs: httpx.Response(503, request=httpx.Request("GET", url))
    )

    signals = _for_company(WebsiteObserver().observe(service), company.id)
    assert [s.kind for s in signals] == ["website_offline"]
    assert "503" in signals[0].detail


def test_healthy_website_produces_nothing(service, monkeypatch):
    service.create_company(Company(name="Fine Co", website="https://fine.example"))
    monkeypatch.setattr(
        httpx, "get", lambda url, **kwargs: httpx.Response(200, request=httpx.Request("GET", url))
    )

    assert WebsiteObserver().observe(service) == []


def test_website_recovery_resolves_the_outage(service, monkeypatch):
    company = service.create_company(Company(name="Flappy Co", website="https://flappy.example"))
    observer = WebsiteObserver()

    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("down")),
    )
    run_observation_cycle(service, [observer])

    monkeypatch.setattr(
        httpx, "get", lambda url, **kwargs: httpx.Response(200, request=httpx.Request("GET", url))
    )
    run_observation_cycle(service, [observer])

    outage = next(s for s in service.list_signals(limit=50) if s.kind == "website_offline")
    assert outage.company_id == company.id
    assert outage.is_open is False


def test_unexpected_failure_is_not_reported_as_downtime(service, monkeypatch):
    """A bug in this observer is not evidence about the site. A false 3am
    'your site is down' costs more trust than a missed one."""
    service.create_company(Company(name="Odd Co", website="https://odd.example"))
    monkeypatch.setattr(
        httpx, "get", lambda url, **kwargs: (_ for _ in ()).throw(ValueError("bad url shape"))
    )

    assert WebsiteObserver().observe(service) == []
