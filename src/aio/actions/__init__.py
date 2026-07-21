"""The action engine: what JARVIS can do, and how it does it.

Importing this package is enough to have a populated catalog -- the
capability modules are imported here for their registration side effect, so
`from aio.actions import available_actions` never returns an empty list just
because nobody remembered to import the catalog first.

The catalog import is deliberately last. `aio.actions.registry` reaches
`aio.connectors` lazily (inside `available_actions`), and the capability
modules import agents, memory, and the LLM layer -- so the primitives are
bound first and this package stays importable on its own, without any
module in the import graph seeing a half-built `aio.actions`.
"""

from __future__ import annotations

from aio.actions.base import (
    ActionContext,
    ActionOutcome,
    ActionResult,
    ActionRisk,
    ActionSpec,
)
from aio.actions.executor import (
    UnknownAction,
    execute_action,
    execute_approved_action,
)
from aio.actions.registry import (
    action,
    all_actions,
    available_actions,
    catalog_for_planner,
    get_action,
)

from aio.actions import catalog as catalog  # noqa: F401  -- registers every action

__all__ = [
    "ActionContext",
    "ActionOutcome",
    "ActionResult",
    "ActionRisk",
    "ActionSpec",
    "UnknownAction",
    "action",
    "all_actions",
    "available_actions",
    "catalog_for_planner",
    "execute_action",
    "execute_approved_action",
    "get_action",
]
