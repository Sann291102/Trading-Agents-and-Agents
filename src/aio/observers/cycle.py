"""One sweep of JARVIS's attention across everything it watches.

This is the Observe half of the executive loop, kept separate from the
Reason/Act half in `aio.os.autonomy` so it can be run, tested, and scheduled
on its own -- watching is cheap and should happen far more often than
thinking, which costs a model call.

The bookkeeping here is what lets observers stay stateless. Each one reports
what is true now; this module works out what that means over time:
  - a condition seen before collapses onto the existing signal (times_seen++)
  - a condition an observer stops reporting is resolved
  - an observer that *failed* resolves nothing, because a crashed observer
    has no opinion about what is still true, and silently closing real
    problems because a token expired would be the worst possible failure
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aio.events.bus import OrgEvent, event_bus
from aio.models.signals import Signal
from aio.observers.base import Observer, all_observers

if TYPE_CHECKING:
    from aio.business.service import BusinessService

logger = logging.getLogger("aio.observers.cycle")


def run_observation_cycle(
    business: "BusinessService", observers: list[Observer] | None = None
) -> list[Signal]:
    """Sweep every available observer. Returns the signals that are *new or
    newly worse* -- not every open condition -- since those are what warrant
    anyone's attention this cycle."""
    watched = observers if observers is not None else all_observers()
    fresh: list[Signal] = []
    total_seen = 0
    resolved = 0
    failed: list[str] = []

    for observer in watched:
        seen = observer.safe_observe(business)
        if seen is None:
            # Unavailable or broken. Not an error worth interrupting the
            # cycle for, but its existing signals stay open.
            if observer.available():
                failed.append(observer.name)
            continue

        keys: set[str] = set()
        for signal in seen:
            keys.add(signal.dedupe_key)
            total_seen += 1
            try:
                stored = business.record_signal(signal)
            except Exception:
                logger.exception("could not record signal %s", signal.dedupe_key)
                continue
            if stored.times_seen == 1:
                fresh.append(stored)
                _publish_signal(stored)

        resolved += business.resolve_signals_absent_from(observer.name, keys)

    _publish_cycle(len(watched), total_seen, len(fresh), resolved, failed)
    return fresh


def _publish_signal(signal: Signal) -> None:
    event_bus.publish(
        OrgEvent(
            type="signal_observed",
            agent_role="JARVIS",
            message=signal.title,
            payload={
                "signal_id": signal.id,
                "source": signal.source,
                "kind": signal.kind,
                "severity": signal.severity,
                "detail": signal.detail,
            },
        )
    )


def _publish_cycle(
    watched: int, seen: int, fresh: int, resolved: int, failed: list[str]
) -> None:
    parts = [f"watched {watched}"]
    if fresh:
        parts.append(f"{fresh} new")
    if resolved:
        parts.append(f"{resolved} resolved")
    if failed:
        parts.append(f"{len(failed)} unavailable")
    message = (
        f"Observation: {', '.join(parts)}."
        if fresh or resolved or failed
        else "Observation: nothing new."
    )
    event_bus.publish(
        OrgEvent(
            type="observation_cycle",
            agent_role="JARVIS",
            department="Executive Office",
            message=message,
            payload={
                "observers": watched,
                "signals_seen": seen,
                "new_signals": fresh,
                "resolved": resolved,
                "failed_observers": failed,
            },
        )
    )
