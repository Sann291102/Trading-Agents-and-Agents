"""The Connector primitive: JARVIS's link to a system it does not own.

An Action is what JARVIS can *do*; a Connector is what it is *plugged into*.
Keeping them separate is what lets the same action catalog behave correctly on
two different founders' machines: the action always exists, but it is only
offered to the autonomous planner when its connector is genuinely configured
(`aio.actions.registry.available_actions`).

Two rules make the rest of the system trustworthy:

`available()` must reflect real configuration, checked live. JARVIS claiming a
capability it does not have is worse than lacking it -- the planner would keep
choosing an action that can only fail, and the founder would be told work
happened when nothing left the building.

`connector_available()` must never raise. It sits inside the loop that builds
the planner's menu, so a typo'd connector name or a connector whose config
lookup blows up has to degrade to "not available", never take down autonomy.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, ClassVar

logger = logging.getLogger("aio.connectors")


class Capability(str, Enum):
    """What kind of reach a connector gives JARVIS into the external system.

    Coarse on purpose: this drives what the founder sees in the connector
    panel and how much authority an action through it implies, not a
    fine-grained permission model.
    """

    READ = "read"
    """Pull information out of the system (search, fetch, list)."""

    WRITE = "write"
    """Create or update content there (a note, a record, a document)."""

    OBSERVE = "observe"
    """Receive events from it -- webhooks, inbound notifications."""

    EXECUTE = "execute"
    """Make it run something on JARVIS's behalf (a workflow, a job)."""


class Connector(ABC):
    """A uniform surface over one external system.

    Subclasses declare their identity as class attributes and implement
    `available()`. Everything the UI needs comes from `status()`, so a new
    connector never requires a frontend change.
    """

    name: ClassVar[str]
    display_name: ClassVar[str]
    description: ClassVar[str]
    capabilities: ClassVar[tuple[Capability, ...]] = ()

    setup_hint: ClassVar[str] = ""
    """Exactly which .env var the founder must set to switch this on. Empty
    for internal connectors, which need no configuration at all."""

    @abstractmethod
    def available(self) -> bool:
        """Whether this connector is configured *right now*.

        Checked live rather than cached: `settings.reload()` lets the founder
        add an API key without restarting the process, and the next call here
        must see it.
        """

    def status(self) -> dict[str, Any]:
        """The connector panel's row. `setup_hint` is blanked once the
        connector works, so the UI can show the hint iff it is non-empty
        instead of deciding when a hint is still relevant."""
        available = self.safe_available()
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "capabilities": [capability.value for capability in self.capabilities],
            "available": available,
            "setup_hint": "" if available else self.setup_hint,
        }

    def safe_available(self) -> bool:
        """`available()` with failures treated as "not available". A broken
        config check must degrade this connector, never break the caller
        enumerating every connector."""
        try:
            return bool(self.available())
        except Exception:  # pragma: no cover - defensive; config reads are cheap
            logger.warning("connector %r availability check failed", self.name, exc_info=True)
            return False

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities


_REGISTRY: dict[str, Connector] = {}


def register_connector(connector: Connector) -> Connector:
    """Add (or replace) a connector by name.

    Replacing rather than rejecting a duplicate is deliberate: registration is
    an import side effect, so it must stay idempotent, and a test swapping in a
    fake connector should not have to reach into the registry dict.
    """
    _REGISTRY[connector.name] = connector
    return connector


def all_connectors() -> list[Connector]:
    return sorted(_REGISTRY.values(), key=lambda connector: connector.name)


def get_connector(name: str) -> Connector | None:
    return _REGISTRY.get(name)


def connector_available(name: str) -> bool:
    """Whether the named connector exists and is configured.

    Returns False for an unknown name instead of raising -- the action
    registry calls this for every action's declared connector while building
    the planner's menu, and a stale or misspelled name there must cost that
    one action, not the whole autonomous cycle.
    """
    connector = _REGISTRY.get(name)
    if connector is None:
        return False
    return connector.safe_available()
