"""Contracts for JARVIS's autonomous executive loop.

The loop is the difference between an assistant that answers when spoken to
and an operator that runs the company between conversations. These are the
two halves of that: how hard the founder lets it run (`AutonomySettings`),
and what it decided to do this cycle (`AutonomyDecision`).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AutonomySettings(BaseModel):
    """The founder's throttle on JARVIS acting unsupervised.

    `enabled` defaults to False on purpose: a fresh install must not start
    operating someone's company before they have switched it on and seen
    what it can do. The Field bounds are guard rails, not preferences -- a
    5-second interval or 50 actions per cycle is never an intentional
    setting, it is a typo that would burn the LLM budget and flood the
    founder's approval queue before anyone noticed.
    """

    enabled: bool = False
    interval_seconds: int = Field(default=900, ge=30, le=86_400)
    max_actions_per_cycle: int = Field(default=2, ge=0, le=10)


class NextAction(BaseModel):
    """One action the planner wants to take, with the reason it chose it.

    `params` is deliberately an untyped dict here: it comes from an LLM and
    is only trusted once the executor has validated it against the target
    action's own `params_model`.
    """

    action: str = Field(..., description="Action name, copied verbatim from the catalog")
    params: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(default="", description="Why this is the highest-leverage move now")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class AutonomyDecision(BaseModel):
    """The planner's structured output for one cycle.

    An empty `actions` list is a legitimate, correct answer. A loop that must
    always produce work invents busywork the founder then has to unpick, so
    idling is modelled as a first-class outcome rather than a failure.

    Every field except `actions` carries a default so that a model which
    omits `observation` or `confidence` still yields a usable decision
    instead of failing schema validation and wasting the whole cycle.
    """

    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reasoning_summary: str = ""
    observation: str = Field(
        default="", description="What JARVIS sees in the business right now"
    )
    actions: list[NextAction] = Field(default_factory=list)
