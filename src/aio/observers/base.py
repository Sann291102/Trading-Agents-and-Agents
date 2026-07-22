"""JARVIS's eyes.

A Connector is how JARVIS *reaches* a system; an Observer is how JARVIS
*watches* one. They are deliberately separate: watching has different
failure semantics from acting. An observer that throws must never take down
the observation cycle, because the whole point is that it runs unattended
forever -- one broken pair of eyes cannot blind the rest.

Every observer returns the complete current truth for its own source on each
pass, rather than a diff. The cycle handles the bookkeeping that turns that
into events: repeats collapse onto one signal, and conditions an observer
stops reporting are resolved automatically. This means an observer is a pure
"what is true right now?" function, which is by far the easiest contract to
implement correctly -- no state, no memory of the last run, no missed edges.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from aio.models.signals import ObserverStatus, Signal

if TYPE_CHECKING:
    from aio.business.service import BusinessService

logger = logging.getLogger("aio.observers")


class Observer(ABC):
    """One thing JARVIS keeps an eye on."""

    name: str = "observer"
    display_name: str = "Observer"
    description: str = ""
    watches: tuple[str, ...] = ()
    setup_hint: str = ""

    def available(self) -> bool:
        """Whether this observer can actually see anything right now.

        Default True for observers that watch JARVIS's own data and need no
        credentials; anything reaching an external system must override this
        with a real config check rather than claiming to be watching.
        """
        return True

    @abstractmethod
    def observe(self, business: "BusinessService") -> list[Signal]:
        """Everything true for this source right now. Must not raise for
        expected conditions (network down, endpoint 500) -- return no signals,
        or a signal describing the outage, whichever is honest."""

    def safe_observe(self, business: "BusinessService") -> list[Signal] | None:
        """`observe` with a seatbelt. Returns None when the observer failed,
        which the cycle distinguishes from "saw nothing": an observer that
        crashed has no opinion about what is still true, so its existing
        signals must not be auto-resolved."""
        if not self.available():
            return None
        try:
            return list(self.observe(business))
        except Exception:
            logger.warning("observer %s failed", self.name, exc_info=True)
            return None

    def status(self) -> ObserverStatus:
        available = self.available()
        return ObserverStatus(
            name=self.name,
            display_name=self.display_name,
            description=self.description,
            available=available,
            setup_hint="" if available else self.setup_hint,
            watches=list(self.watches),
        )


_REGISTRY: dict[str, Observer] = {}


def register_observer(observer: Observer) -> Observer:
    """Replaces on duplicate name so import-time registration stays
    idempotent and a test can swap in a fake."""
    _REGISTRY[observer.name] = observer
    return observer


def all_observers() -> list[Observer]:
    return sorted(_REGISTRY.values(), key=lambda o: o.name)


def get_observer(name: str) -> Observer | None:
    return _REGISTRY.get(name)


def available_observers() -> list[Observer]:
    out: list[Observer] = []
    for observer in all_observers():
        try:
            if observer.available():
                out.append(observer)
        except Exception:
            logger.warning("observer %s availability check failed", observer.name, exc_info=True)
    return out
