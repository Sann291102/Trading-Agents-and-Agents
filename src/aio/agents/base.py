"""Common shape for every department agent.

A real department in the full org-wide architecture is a whole squad of
specialists; in this vertical slice each department is represented by one
agent with a narrow, explicit responsibility. New agents (Frontend Lead, QA
Engineer, Security Officer, ...) are added by subclassing `Agent` and giving
it a role and system prompt -- they don't need any other wiring to be
callable, only to be added to the orchestration graph.

`run()` is the original, minimal interface (still used as-is by the
Executive/Product Manager/Backend Lead department leads). `run_logged()`
wraps it with timing, structured logging, and optional persistence to
long-term memory, for free-text calls. `run_logged_json()` is the same for
calls that parse the response into a Pydantic model -- it logs *after*
parsing so the real `confidence`/`reasoning_summary` on the parsed model
(every research/product schema carries both) end up on the
ExecutionMetrics/OrgEvent, not blank placeholders; logging immediately
after the raw LLM call, before parsing, would only ever see whatever
confidence the *caller* already knew, which is nothing in every case that
matters. `plan`/`execute`/`review`/`handoff` are the generic lifecycle
hooks new agents are expected to implement; department leads predating
this lifecycle keep their own, more specific method names (e.g.
`ExecutiveAgent.plan(goal)` / `.review(goal, requirements, tech_plan)`)
rather than being forced to conform retroactively.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, TypeVar

from aio.agents.parsing import parse_json_response
from aio.events.bus import OrgEvent, event_bus
from aio.llm.anthropic_client import AnthropicClient
from aio.observability.context import current_project_id
from aio.observability.execution_log import ExecutionMetrics
from aio.orchestration import cancellation
from aio.orchestration.cancellation import MissionCancelled

if TYPE_CHECKING:
    from pydantic import BaseModel

    from aio.memory.long_term import LongTermMemory

ModelT = TypeVar("ModelT", bound="BaseModel")


class Agent:
    role: str = "agent"
    department: str = "General"
    system_prompt: str = "You are a helpful assistant."
    input_schema: "type[BaseModel] | None" = None
    output_schema: "type[BaseModel] | None" = None

    def __init__(self, llm: AnthropicClient, long_term: "LongTermMemory | None" = None) -> None:
        self._llm = llm
        self._long_term = long_term
        self._logger = logging.getLogger(f"aio.agents.{self.role.lower().replace(' ', '_')}")

    def run(self, task: str, max_tokens: int = 20000) -> str:
        return self._llm.complete(system=self.system_prompt, user=task, max_tokens=max_tokens)

    def _mark_started(self) -> tuple[datetime, float]:
        started_at = datetime.now(timezone.utc)
        t0 = time.monotonic()
        event_bus.publish(
            OrgEvent(
                type="agent_started",
                department=self.department,
                agent_role=self.role,
                project_id=current_project_id.get(),
                message=f"{self.role} started",
            )
        )
        return started_at, t0

    def _finish(
        self,
        started_at: datetime,
        t0: float,
        *,
        handoff_target: str | None,
        confidence: float | None = None,
        reasoning_summary: str = "",
        error: str | None = None,
    ) -> ExecutionMetrics:
        metrics = ExecutionMetrics(
            agent_role=self.role,
            started_at=started_at,
            ended_at=datetime.now(timezone.utc),
            duration_seconds=time.monotonic() - t0,
            confidence=confidence,
            reasoning_summary=reasoning_summary,
            handoff_target=handoff_target,
            error=error,
        )
        self._log(metrics)
        return metrics

    def run_logged(
        self,
        task: str,
        *,
        max_tokens: int = 20000,
        handoff_target: str | None = None,
        confidence: float | None = None,
        reasoning_summary: str = "",
    ) -> tuple[str, ExecutionMetrics]:
        """Like `run`, but times the call and records an ExecutionMetrics
        entry (logged always; persisted if this agent has long-term memory).

        For free-text calls with no structured confidence to report (CEO's
        plan/review, Research Coordinator's plan, Backend Lead's technical
        plan). Calls that parse the response into a Pydantic model with its
        own `confidence`/`reasoning_summary` fields should use
        `run_logged_json` instead, so those real values reach the metrics
        instead of the blanks this method would otherwise log.
        """
        if cancellation.is_cancelled(current_project_id.get()):
            raise MissionCancelled
        started_at, t0 = self._mark_started()
        try:
            text = self.run(task, max_tokens=max_tokens)
        except Exception as exc:
            self._finish(started_at, t0, handoff_target=handoff_target, error=str(exc))
            raise
        metrics = self._finish(
            started_at,
            t0,
            handoff_target=handoff_target,
            confidence=confidence,
            reasoning_summary=reasoning_summary,
        )
        return text, metrics

    def run_logged_json(
        self,
        task: str,
        model: type[ModelT],
        *,
        max_tokens: int = 20000,
        handoff_target: str | None = None,
    ) -> ModelT:
        """Like `run_logged`, but parses the response into `model` and logs
        *after* parsing, using the parsed object's own `confidence`/
        `reasoning_summary` fields -- every research/product schema in
        `aio.models` carries both, so this is how a real confidence score
        ends up on the ExecutionMetrics/OrgEvent instead of always being
        `None` (logging immediately after the raw LLM call, before parsing,
        can only ever see a confidence the caller already knew -- which is
        nothing, for every current call site).
        """
        if cancellation.is_cancelled(current_project_id.get()):
            raise MissionCancelled
        started_at, t0 = self._mark_started()
        try:
            text = self.run(task, max_tokens=max_tokens)
            parsed = parse_json_response(text, model)
        except Exception as exc:
            self._finish(started_at, t0, handoff_target=handoff_target, error=str(exc))
            raise
        self._finish(
            started_at,
            t0,
            handoff_target=handoff_target,
            confidence=getattr(parsed, "confidence", None),
            reasoning_summary=getattr(parsed, "reasoning_summary", ""),
        )
        return parsed

    def _log(self, metrics: ExecutionMetrics) -> None:
        if metrics.error:
            self._logger.error(
                "execution failed duration=%.3fs error=%s",
                metrics.duration_seconds,
                metrics.error,
            )
            message = f"{self.role} failed: {metrics.error}"
        else:
            self._logger.info(
                "execution complete duration=%.3fs confidence=%s handoff=%s",
                metrics.duration_seconds,
                metrics.confidence,
                metrics.handoff_target,
            )
            confidence_note = (
                f" (confidence {metrics.confidence:.2f})" if metrics.confidence is not None else ""
            )
            message = f"{self.role} completed{confidence_note}"

        event_bus.publish(
            OrgEvent(
                type="agent_finished",
                department=self.department,
                agent_role=self.role,
                project_id=current_project_id.get(),
                confidence=metrics.confidence,
                duration_seconds=metrics.duration_seconds,
                message=message,
                payload={"handoff_target": metrics.handoff_target, "error": metrics.error},
            )
        )

        if self._long_term is not None:
            self._long_term.save_execution_log(metrics, project_id=current_project_id.get())

    # -- Generic lifecycle hooks for new agents ---------------------------
    # Concrete research-department agents override these. Not abstract
    # (no ABCMeta) so existing department leads that don't use this
    # lifecycle aren't forced to implement no-op versions.
    def plan(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def review(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def handoff(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError
