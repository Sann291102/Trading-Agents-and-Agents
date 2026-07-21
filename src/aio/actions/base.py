"""The Action primitive: the unit of work JARVIS performs.

JARVIS is an operator, not a reporting tool. Everything it can *do* is an
Action -- a named, parameter-validated, executable capability -- rather than
advice it hands back to the founder. "Record TradeW's metrics", "delegate the
MVP scope to the Operations Director", "file this decision to memory" are all
Actions, and the autonomous loop, the voice assistant, and the HTTP API all
reach work through this same registry.

The autonomy rule lives here, in `ActionRisk`. An action that is reversible
and stays inside JARVIS's own systems runs without asking. An action that is
irreversible, spends money, or is visible to someone outside the company must
be approved by the founder first -- so it is proposed, parked as an Approval
carrying its own parameters, and executed only once approved. That is what
makes approving something in the UI actually *do* the thing rather than just
mark a row as read.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from aio.business.service import BusinessService


class ActionRisk(str, Enum):
    """How much authority an action needs before it may run."""

    SAFE = "safe"
    """Reversible and internal to JARVIS. Runs autonomously, no approval."""

    SENSITIVE = "sensitive"
    """Irreversible, outward-facing, or spends money -- e.g. sending a mail,
    publishing a post, paying an invoice. Always proposed for approval first,
    never executed straight from the autonomous loop."""


class ActionOutcome(str, Enum):
    EXECUTED = "executed"
    ESCALATED = "escalated"  # parked as an Approval, awaiting the founder
    FAILED = "failed"
    REJECTED = "rejected"  # the founder declined it


class ActionResult(BaseModel):
    """What happened when an action ran. `data` carries anything a caller
    (or the next loop iteration) needs -- created ids, agent output, counts."""

    outcome: ActionOutcome
    summary: str = Field(..., description="One line, past tense, for the activity feed")
    detail: str = ""
    data: dict[str, Any] = Field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.outcome is ActionOutcome.EXECUTED


@dataclass(frozen=True)
class ActionContext:
    """Everything a handler is allowed to touch. Passed in rather than
    imported so actions stay testable against an in-memory BusinessService
    and so the executor controls what each action can reach."""

    business: "BusinessService"
    actor: str = "JARVIS"  # which agent (or the founder) triggered this
    long_term: Any = None
    memory: Any = None
    semantic: Any = None


@dataclass(frozen=True)
class ActionSpec:
    """A registered capability. `params_model` is the validation boundary:
    the autonomous loop asks an LLM for parameters, so they are never trusted
    -- they are parsed into this model before the handler ever sees them."""

    name: str
    description: str
    risk: ActionRisk
    params_model: type[BaseModel]
    handler: Callable[[ActionContext, BaseModel], ActionResult]
    owner_agent: str = "Chief of Staff"
    connector: str | None = None
    """Which connector this needs, if any. Unavailable connector -> the action
    is listed but not offered to the planner."""

    def describe(self) -> dict[str, Any]:
        """The catalog entry -- also what the planner sees when choosing an
        action, so the parameter schema travels with the description."""
        return {
            "name": self.name,
            "description": self.description,
            "risk": self.risk.value,
            "owner_agent": self.owner_agent,
            "connector": self.connector,
            "params_schema": self.params_model.model_json_schema(),
        }
