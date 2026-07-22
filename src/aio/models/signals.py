"""What JARVIS notices without being asked.

An Action is JARVIS doing something. A Signal is JARVIS *seeing* something --
a fact about the world or about the business that nobody typed in. Observers
produce them on every observation cycle; the autonomous loop consumes them as
its Observe stage, which is what lets work start from a real event rather
than from a founder's instruction.

The dedupe key is the load-bearing detail. Most signals describe a standing
condition ("this milestone is blocked", "the site is down"), not a moment, so
a naive observer would re-raise the same fact every cycle and bury the feed.
Instead a repeat observation of an unresolved condition bumps `times_seen`
and `last_seen_at` on the existing row. That also turns duration into data:
"blocked, seen 14 times over 3 days" is a much stronger prompt for the
executive loop than "blocked".
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


SignalSeverity = Literal["info", "notable", "urgent"]


class Signal(BaseModel):
    """One observation. `kind` is the machine-readable event name
    (customer_signed_up, website_offline, milestone_blocked); `title` is the
    one line a human reads in the feed."""

    id: str = Field(default_factory=_uuid)
    source: str = Field(..., description="Observer that saw it, e.g. 'business_state'")
    kind: str = Field(..., description="Event name, e.g. 'milestone_blocked'")
    title: str = Field(..., description="One line, human-readable")
    detail: str = ""
    severity: SignalSeverity = "info"
    company_id: str | None = None

    dedupe_key: str = Field(
        ...,
        description="Stable identity of the underlying condition, not the moment",
    )
    times_seen: int = 1
    observed_at: datetime = Field(default_factory=_now)
    last_seen_at: datetime = Field(default_factory=_now)

    # Set once the executive loop has taken this into account. Unprocessed
    # signals are the loop's inbox; processing is what stops it reacting to
    # the same fact forever.
    processed_at: datetime | None = None
    resolved_at: datetime | None = Field(
        default=None,
        description="Set when the underlying condition stops being observed",
    )

    @property
    def is_open(self) -> bool:
        return self.resolved_at is None

    def as_prompt_line(self) -> str:
        """How this reads to the executive loop. Age and repetition are
        included because a condition seen once is noise and the same
        condition seen twenty times is the most important thing on the
        page."""
        seen = f", seen {self.times_seen}x" if self.times_seen > 1 else ""
        scope = f" [{self.severity}]" if self.severity != "info" else ""
        detail = f" -- {self.detail}" if self.detail else ""
        return f"({self.source}/{self.kind}){scope} {self.title}{detail}{seen}"


class ObserverStatus(BaseModel):
    """What the founder sees on the observer roster: whether each pair of
    eyes is actually open, and what to configure if not."""

    name: str
    display_name: str
    description: str
    available: bool
    setup_hint: str = ""
    watches: list[str] = Field(
        default_factory=list, description="Signal kinds this observer can raise"
    )
