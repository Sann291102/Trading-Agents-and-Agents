"""The template for an observer that lives behind a credential.

Where `business_state` proves the loop works with nothing configured, this
one shows the shape every future integration observer takes: `available()`
is a real config check, so an unkeyed install simply never runs it -- no
errors, no empty panels, no pretending to watch something.

Two details are the actual lesson here, not the GitHub API:

`available()` reads the token through `getattr(settings, ...)` because the
setting may not exist on `Settings` yet. An observer must degrade to "off"
against an older config object rather than crash the whole cycle at import.

And a failed API call raises instead of returning `[]`. That is the opposite
of the usual "swallow it" reflex, and it is deliberate: an empty list is a
positive claim that nothing is wrong, and the cycle would resolve every open
GitHub signal on the strength of it. A raise reaches `safe_observe`, which
returns None -- "this observer has no opinion right now" -- and existing
signals correctly stay open.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import httpx

from aio.config import settings
from aio.models.signals import Signal
from aio.observers.base import Observer, register_observer

if TYPE_CHECKING:
    from aio.business.service import BusinessService

_API_ROOT = "https://api.github.com"
_TIMEOUT_SECONDS = 10.0

# A pull request open this long is not "in review", it is forgotten.
_PR_STALE_AFTER = timedelta(days=3)

# Below this an issue list is a backlog; above it, it is a signal that triage
# has stopped happening.
_ISSUE_PILEUP = 10


def _setting(name: str, env_var: str) -> str:
    """Config first, environment as the fallback -- `Settings` ignores unknown
    env vars, so a GITHUB_TOKEN in `.env` would otherwise be invisible until
    someone adds the field to config.py (which this module does not own)."""
    return (getattr(settings, name, "") or os.environ.get(env_var, "")).strip()


def _age(iso: str, now: datetime) -> timedelta:
    # GitHub timestamps are RFC 3339 with a trailing Z.
    return now - datetime.fromisoformat(iso.replace("Z", "+00:00"))


class GitHubObserver(Observer):
    """Watches one configured repository for work that has stalled."""

    name = "github"
    display_name = "GitHub"
    description = "Watches a repository for review queues and issue pile-ups."
    watches = ("github_pr_waiting", "github_issues_open")
    setup_hint = (
        "Set GITHUB_TOKEN in .env (a personal access token with read access to the "
        "repo), and GITHUB_REPO to the repository to watch as 'owner/name'."
    )

    def available(self) -> bool:
        return bool(_setting("github_token", "GITHUB_TOKEN"))

    def observe(self, business: "BusinessService") -> list[Signal]:
        repo = _setting("github_repo", "GITHUB_REPO")
        if not repo:
            # Keyed but pointed at nothing. There is genuinely nothing to
            # watch, so reporting nothing is honest rather than blind.
            return []

        now = datetime.now(timezone.utc)
        items = self._open_items(repo)

        signals: list[Signal] = []
        issues = [i for i in items if "pull_request" not in i]

        for pull in (i for i in items if "pull_request" in i):
            waiting = _age(pull["created_at"], now)
            if waiting < _PR_STALE_AFTER:
                continue
            signals.append(
                Signal(
                    source=self.name,
                    kind="github_pr_waiting",
                    title=f"PR #{pull['number']} has been open {waiting.days}d: {pull['title']}",
                    detail=f"{repo} -- {pull.get('html_url', '')}",
                    severity="notable",
                    dedupe_key=f"github_pr:{repo}:{pull['number']}",
                )
            )

        if len(issues) >= _ISSUE_PILEUP:
            signals.append(
                Signal(
                    source=self.name,
                    kind="github_issues_open",
                    title=f"{len(issues)} open issues on {repo}",
                    detail="Issue triage has fallen behind.",
                    severity="notable",
                    # Not keyed on the count: the condition is "the backlog is
                    # unmanaged", and re-raising it on every new issue would
                    # bury the feed.
                    dedupe_key=f"github_issues:{repo}",
                )
            )
        return signals

    def _open_items(self, repo: str) -> list[dict]:
        """Open issues *and* pull requests -- GitHub's issues endpoint returns
        both, and PRs are distinguished by a `pull_request` key."""
        response = httpx.get(
            f"{_API_ROOT}/repos/{repo}/issues",
            params={"state": "open", "per_page": 100},
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {_setting('github_token', 'GITHUB_TOKEN')}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []


register_observer(GitHubObserver())
