"""The catalog of everything JARVIS can do.

Actions register themselves with the `@action` decorator at import time, the
same way agents register by subclassing `Agent` -- adding a capability means
writing one function, not also editing a list. `aio.actions.catalog` imports
every catalog module for this side effect.

`available_actions()` is deliberately separate from `all_actions()`: an action
whose connector is not configured still exists (so the UI can show what JARVIS
*could* do once connected) but must never be offered to the autonomous
planner, which would otherwise keep choosing an action that cannot run.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from aio.actions.base import ActionContext, ActionResult, ActionRisk, ActionSpec

_REGISTRY: dict[str, ActionSpec] = {}


def action(
    name: str,
    *,
    description: str,
    risk: ActionRisk,
    params_model: type[BaseModel],
    owner_agent: str = "Chief of Staff",
    connector: str | None = None,
) -> Callable:
    """Register a handler as a named capability.

    The handler takes (ActionContext, params) and returns an ActionResult.
    Raising is allowed -- the executor converts it into a FAILED result so a
    broken action can never take down the autonomous loop.
    """

    def decorator(handler: Callable[[ActionContext, BaseModel], ActionResult]):
        if name in _REGISTRY:
            raise ValueError(f"duplicate action name {name!r}")
        _REGISTRY[name] = ActionSpec(
            name=name,
            description=description,
            risk=risk,
            params_model=params_model,
            handler=handler,
            owner_agent=owner_agent,
            connector=connector,
        )
        return handler

    return decorator


def all_actions() -> list[ActionSpec]:
    return sorted(_REGISTRY.values(), key=lambda spec: spec.name)


def get_action(name: str) -> ActionSpec | None:
    return _REGISTRY.get(name)


def available_actions() -> list[ActionSpec]:
    """Actions that can actually run right now -- every action with no
    connector requirement, plus those whose connector is configured."""
    from aio.connectors import connector_available

    return [
        spec
        for spec in all_actions()
        if spec.connector is None or connector_available(spec.connector)
    ]


def catalog_for_planner() -> str:
    """The action menu handed to the LLM when it decides what JARVIS should
    do next. Only runnable actions appear, and each carries its risk so the
    planner knows what will execute immediately versus what will be parked
    for the founder's approval."""
    lines: list[str] = []
    for spec in available_actions():
        params = ", ".join(spec.params_model.model_fields) or "no parameters"
        lines.append(
            f"- {spec.name} ({spec.risk.value}): {spec.description} "
            f"[params: {params}]"
        )
    return "\n".join(lines) or "No actions are currently available."
