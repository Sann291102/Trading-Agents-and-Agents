"""Runs actions, enforces the autonomy rule, and records what happened.

Every path into "JARVIS does something" -- the autonomous loop, the voice
assistant, an HTTP call -- funnels through `execute_action` so that the
authority check, the audit trail, and the activity events exist exactly once.

The autonomy rule: a SAFE action runs immediately; a SENSITIVE action is
parked as an Approval carrying its own name and parameters, so that approving
it later re-enters this module via `execute_approved_action` and actually
performs the work. An approval in this system is a deferred action, not a
notification.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ValidationError

from aio.actions.base import ActionContext, ActionOutcome, ActionResult, ActionRisk, ActionSpec
from aio.actions.registry import get_action
from aio.events.bus import OrgEvent, event_bus
from aio.models.business import Approval

logger = logging.getLogger("aio.actions.executor")


class UnknownAction(RuntimeError):
    pass


def _publish(spec_name: str, actor: str, result: ActionResult) -> None:
    event_bus.publish(
        OrgEvent(
            type="action_executed" if result.ok else "action_escalated"
            if result.outcome is ActionOutcome.ESCALATED
            else "action_failed",
            agent_role=actor,
            message=result.summary,
            payload={
                "action": spec_name,
                "outcome": result.outcome.value,
                "detail": result.detail,
            },
        )
    )


def _record(context: ActionContext, spec_name: str, params: dict, result: ActionResult) -> None:
    """Persist the run so the activity feed and JARVIS's own memory of what
    it has already done survive a restart."""
    try:
        context.business.record_action_run(
            action=spec_name,
            actor=context.actor,
            params=params,
            outcome=result.outcome.value,
            summary=result.summary,
            detail=result.detail,
        )
    except Exception:  # pragma: no cover - audit must never break execution
        logger.exception("failed to record action run for %s", spec_name)


def _validate(spec: ActionSpec, params: dict) -> BaseModel:
    return spec.params_model.model_validate(params or {})


def execute_action(
    name: str,
    params: dict,
    context: ActionContext,
    *,
    pre_approved: bool = False,
) -> ActionResult:
    """Run a named action.

    `pre_approved` is set only when the founder has explicitly approved this
    exact action (or invoked it directly from the UI); the autonomous loop
    never passes it, which is what keeps sensitive work behind approval.
    """
    spec = get_action(name)
    if spec is None:
        raise UnknownAction(f"no action named {name!r}")

    try:
        parsed = _validate(spec, params)
    except ValidationError as exc:
        result = ActionResult(
            outcome=ActionOutcome.FAILED,
            summary=f"Could not run {name}: parameters were invalid",
            detail=str(exc),
        )
        _record(context, name, params, result)
        _publish(name, context.actor, result)
        return result

    if spec.risk is ActionRisk.SENSITIVE and not pre_approved:
        approval = context.business.create_approval(
            Approval(
                title=f"Approve: {spec.description}",
                detail=_approval_detail(spec, parsed),
                requested_by=context.actor,
                pending_action=name,
                pending_params_json=json.dumps(parsed.model_dump(mode="json")),
            )
        )
        result = ActionResult(
            outcome=ActionOutcome.ESCALATED,
            summary=f"Needs your approval: {spec.description}",
            detail="Parked until approved -- it will run automatically once you approve it.",
            data={"approval_id": approval.id},
        )
        _record(context, name, params, result)
        _publish(name, context.actor, result)
        return result

    try:
        result = spec.handler(context, parsed)
    except Exception as exc:
        logger.exception("action %s failed", name)
        result = ActionResult(
            outcome=ActionOutcome.FAILED,
            summary=f"{spec.description} failed",
            detail=str(exc),
        )

    _record(context, name, parsed.model_dump(mode="json"), result)
    _publish(name, context.actor, result)
    return result


def execute_approved_action(approval_id: str, context: ActionContext) -> ActionResult | None:
    """Perform the work an approval was holding. Returns None when the
    approval carried no action (a plain note the founder just acknowledged),
    which is not an error."""
    approval = context.business.get_approval(approval_id)
    if approval is None or not approval.pending_action:
        return None

    params = json.loads(approval.pending_params_json) if approval.pending_params_json else {}
    return execute_action(approval.pending_action, params, context, pre_approved=True)


def _approval_detail(spec: ActionSpec, params: BaseModel) -> str:
    """Show the founder exactly what will happen if they approve -- the
    parameters, spelled out, not just the action name."""
    fields = params.model_dump(mode="json")
    if not fields:
        return spec.description
    rendered = "\n".join(f"  {key}: {value}" for key, value in fields.items())
    return f"{spec.description}\n{rendered}"
