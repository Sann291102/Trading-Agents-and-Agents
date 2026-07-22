"""The thinking half of JARVIS's autonomous executive loop.

Observe -> Reason -> Prioritize -> Execute -> Verify -> Learn, as plain
synchronous code with no asyncio anywhere in it. `kernel.py` owns *when* a
cycle runs; this module owns *what* the cycle decides and does, which is the
part worth unit-testing and the part a "run a cycle now" endpoint can call
directly.

The stages map onto real objects rather than prose:
  Observe    -- `run_observation_cycle()` sweeps JARVIS's watchers, and
                `business.signal_inbox()` puts what they saw in front of the
                planner; `business.snapshot_for_briefing()` is only the
                background those observations happened against
  Reason     -- one LLM call producing an `AutonomyDecision`
  Prioritize -- the decision is capped at `limit` actions, highest leverage first
  Execute    -- `execute_action`, never `pre_approved`, so sensitive work parks
                as an Approval instead of happening behind the founder's back
  Verify     -- each `ActionResult` carries its own outcome; nothing is assumed
  Learn      -- every run is persisted, and `recent_action_summary()` feeds the
                next cycle's prompt so JARVIS does not re-propose what it just did

Resilience is a hard requirement here, not politeness: this runs unattended
on a timer. A bad LLM response, a mis-named action, or one exploding handler
must cost at most a single cycle -- never the loop.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from aio.actions.base import ActionContext, ActionOutcome, ActionResult
from aio.actions.executor import execute_action
from aio.actions.registry import catalog_for_planner, get_action
from aio.agents.parsing import json_response_instruction, parse_json_response
from aio.events.bus import OrgEvent, event_bus
from aio.models.autonomy import AutonomyDecision

if TYPE_CHECKING:
    from aio.business.service import BusinessService
    from aio.models.signals import Signal

logger = logging.getLogger("aio.os.autonomy")

_MAX_TOKENS = 4000


def _system_prompt(limit: int) -> str:
    """The operator's charter.

    Starts with "You are the Autonomous Operator," because
    `extract_role_from_system_prompt` keys the demo provider (and the test
    fakes) off that exact prefix -- see agents/parsing.py.
    """
    return (
        "You are the Autonomous Operator, the always-on executive loop inside "
        "JARVIS. You run a founder's company while they are not watching.\n\n"
        "You do not give advice, write reports, or describe what someone should "
        "do. You choose the highest-leverage work that moves the business "
        "forward right now, and you perform it by choosing actions.\n\n"
        "You are reactive. Every cycle begins with what has been OBSERVED -- "
        "things JARVIS's watchers saw that nobody typed in. Those observations "
        "are your reason to act; the state of the business is only the "
        "background they happened against.\n\n"
        "Rules:\n"
        f"- Choose at most {limit} action(s) this cycle, best first.\n"
        "- React to the observations. Ones marked [urgent], and ones seen many "
        "times, are the ones that have been ignored longest -- handle those "
        "first.\n"
        "- An observation that needs no action is fine to leave alone. You have "
        "read it; not every observed fact deserves a response.\n"
        "- Every `action` value MUST be copied verbatim from the catalog below. "
        "An action that is not in the catalog does not exist and will be discarded.\n"
        "- Every `params` object MUST use that action's exact parameter names.\n"
        "- Prefer doing the work over asking the founder a question.\n"
        "- Never repeat work that already appears in the recent-actions log.\n"
        "- Actions marked (sensitive) are irreversible, outward-facing, or spend "
        "money: choosing one parks it for the founder's approval instead of "
        "running it, so propose one only when the work genuinely needs sign-off.\n"
        "- If nothing is worth doing right now, return an empty actions list. "
        "Idling is a correct answer; inventing busywork is not.\n\n"
        f"{json_response_instruction(AutonomyDecision)}"
    )


def plan_next_actions(
    business: "BusinessService",
    llm: Any,
    *,
    limit: int,
    inbox: str | None = None,
) -> AutonomyDecision:
    """Decide what JARVIS should do next, grounded in what is actually true.

    Four inputs, each load-bearing: what was observed (so the plan is a
    *response* to something rather than a timer firing), the company's real
    state (so it is about this business), what JARVIS already did (so it does
    not loop on the same idea forever), and the action catalog (so the plan is
    executable rather than a wish).

    The signal inbox goes first because that is the ranking the operator
    should read the cycle in: the world changed, here is the background,
    here is what you may do about it.

    `inbox` may be supplied by a caller that already rendered it, so that the
    text shown to the model and the signals that caller marks processed are
    provably the same set rather than two independent reads.
    """
    system = _system_prompt(limit)
    if inbox is None:
        inbox = business.signal_inbox()
    user = (
        "OBSERVED -- what JARVIS has noticed and you have not yet responded to. "
        "This is why this cycle is running:\n"
        f"{inbox}\n\n"
        "Background -- current state of the business:\n"
        f"{business.snapshot_for_briefing()}\n\n"
        "What you have already done recently -- do not repeat any of it:\n"
        f"{business.recent_action_summary()}\n\n"
        "Actions available to you:\n"
        f"{catalog_for_planner()}\n\n"
        "Decide what to do next."
    )
    decision = parse_json_response(
        llm.complete(system=system, user=user, max_tokens=_MAX_TOKENS),
        AutonomyDecision,
    )
    # The cap is enforced here, not trusted to the prompt: a model that
    # returns six actions must not get six actions' worth of authority.
    decision.actions = decision.actions[: max(0, limit)]
    return decision


def _observe(business: "BusinessService") -> list["Signal"]:
    """Look before thinking, and never let looking cost the cycle.

    Imported lazily so this module stays importable without the observers
    package: `aio.os.autonomy` is on the API's import path, and a missing or
    broken pair of eyes must degrade to "plan on the last known state", not
    to an import error at startup.
    """
    try:
        from aio.observers.cycle import run_observation_cycle
    except ImportError:
        logger.debug("observers package unavailable -- skipping the observe step")
        return []
    except Exception:
        # A built-in observer that explodes at import time would otherwise
        # take the cycle with it, since this call sits outside the planning
        # guard below.
        logger.exception("observers package could not be imported")
        return []
    try:
        return list(run_observation_cycle(business))
    except Exception:
        logger.exception("observation failed -- reasoning on already-known signals")
        return []


def run_cycle(
    business: "BusinessService",
    *,
    context_factory: Callable[[], ActionContext],
    llm: Any = None,
    limit: int = 2,
    observe: bool = True,
) -> list[ActionResult]:
    """Run one full autonomous cycle and return what came of it.

    `observe=True` makes a single call genuinely Observe -> Reason -> Act. The
    kernel can also watch on its own faster clock, in which case the sweep
    here is what guarantees the planner reasons about the world as of *now*
    rather than as of the last cheap pass.

    `context_factory` is injected rather than built here so the caller
    controls which BusinessService/memory an action can reach -- the kernel
    passes app state, tests pass an in-memory service.
    """
    if llm is None:
        from aio.llm import build_default_llm

        llm = build_default_llm()

    observed = _observe(business) if observe else []

    # Captured before planning, because these exact ids are what the planner
    # is about to be shown. Marking them afterwards is what stops the loop
    # reacting to the same standing condition every cycle forever.
    considered: list[str] = []

    try:
        inbox = business.signal_inbox()
        considered = _signals_in(business, inbox)
        decision = plan_next_actions(business, llm, limit=limit, inbox=inbox)
    except Exception as exc:
        # A malformed or failed plan costs this cycle only. The next one
        # starts from the same state and can succeed. The signals stay
        # unprocessed on purpose: nothing ever reasoned about them.
        logger.exception("autonomy planning failed")
        _publish_cycle(
            f"Autonomy cycle skipped -- planning failed: {exc}",
            {
                "executed": 0,
                "escalated": 0,
                "failed": 0,
                "error": str(exc),
                "new_signals": len(observed),
                "signals_considered": 0,
                "signals_processed": 0,
            },
        )
        return []

    results: list[ActionResult] = []
    skipped: list[str] = []
    context: ActionContext | None = None

    for chosen in decision.actions:
        if get_action(chosen.action) is None:
            # Hallucinated action names are expected, not exceptional: the
            # planner is an LLM. Drop them and keep the cycle going.
            logger.warning("planner chose unknown action %r -- skipped", chosen.action)
            skipped.append(chosen.action)
            continue
        try:
            if context is None:
                context = context_factory()
            # Never pre_approved: sensitive work must reach the founder.
            results.append(execute_action(chosen.action, chosen.params, context))
        except Exception as exc:
            logger.exception("autonomous action %s could not be run", chosen.action)
            results.append(
                ActionResult(
                    outcome=ActionOutcome.FAILED,
                    summary=f"Could not run {chosen.action}",
                    detail=str(exc),
                )
            )

    # Even a cycle that chose no actions has considered these signals, and
    # deciding nothing was needed is a real decision -- leaving them
    # unprocessed would make the next cycle re-litigate the same facts.
    processed = _mark_processed(business, considered)

    payload = _cycle_payload(decision, results, skipped)
    payload["new_signals"] = len(observed)
    payload["signals_considered"] = len(considered)
    payload["signals_processed"] = processed
    _publish_cycle(_cycle_message(results, skipped), payload)
    return results


def _signals_in(business: "BusinessService", inbox: str) -> list[str]:
    """Ids of exactly the signals the planner is being shown, and no others.

    `signal_inbox()` ranks and truncates, so with more open observations than
    it prints, "everything open and unprocessed" is a strictly larger set than
    "what the model read". Marking the difference processed would retire
    conditions nobody ever reasoned about -- permanently, because a repeat
    observation bumps `times_seen` on the existing row and never clears
    `processed_at`. Matching the rendered lines keeps this correct whatever
    ranking or cap the inbox chooses.
    """
    shown = {line.strip() for line in inbox.splitlines() if line.strip()}
    if not shown:
        return []
    # Same candidate pool signal_inbox() ranks over, so nothing it could have
    # printed is missing from this list.
    return [
        s.id
        for s in business.list_signals(limit=100, open_only=True, unprocessed_only=True)
        if s.as_prompt_line() in shown
    ]


def _mark_processed(business: "BusinessService", signal_ids: list[str]) -> int:
    """Bookkeeping must not discard work that already happened -- the actions
    in this cycle ran whether or not the inbox can be updated."""
    if not signal_ids:
        return 0
    try:
        return business.mark_signals_processed(signal_ids)
    except Exception:
        logger.exception("could not mark %d signal(s) processed", len(signal_ids))
        return 0


def _count(results: list[ActionResult], outcome: ActionOutcome) -> int:
    return sum(1 for r in results if r.outcome is outcome)


def _cycle_message(results: list[ActionResult], skipped: list[str]) -> str:
    if not results and not skipped:
        return "Autonomy cycle: nothing worth doing right now."
    parts = [f"{_count(results, ActionOutcome.EXECUTED)} executed"]
    escalated = _count(results, ActionOutcome.ESCALATED)
    if escalated:
        parts.append(f"{escalated} awaiting your approval")
    failed = _count(results, ActionOutcome.FAILED)
    if failed:
        parts.append(f"{failed} failed")
    if skipped:
        parts.append(f"{len(skipped)} skipped")
    return f"Autonomy cycle: {', '.join(parts)}."


def _cycle_payload(
    decision: AutonomyDecision, results: list[ActionResult], skipped: list[str]
) -> dict[str, Any]:
    return {
        "observation": decision.observation,
        "reasoning_summary": decision.reasoning_summary,
        "confidence": decision.confidence,
        "executed": _count(results, ActionOutcome.EXECUTED),
        "escalated": _count(results, ActionOutcome.ESCALATED),
        "failed": _count(results, ActionOutcome.FAILED),
        "skipped_unknown_actions": skipped,
        "summaries": [r.summary for r in results],
    }


def _publish_cycle(message: str, payload: dict[str, Any]) -> None:
    """One event per cycle, so the founder's feed shows JARVIS thinking even
    on the cycles where it correctly decided to do nothing."""
    event_bus.publish(
        OrgEvent(
            type="autonomy_cycle",
            agent_role="JARVIS",
            department="Executive Office",
            message=message,
            payload=payload,
        )
    )
