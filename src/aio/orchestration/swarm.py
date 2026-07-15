"""Engineering Swarm: the execution half of the organization.

The research pipeline (graph.py) ends with the Executive approving a tech
plan. This module turns that plan into work: the Queen Coordinator
decomposes it into assignments for the ruflo specialist agents, the
assigned specialists run concurrently, and the Production Validator gates
the combined output. graph.py wires these three steps in as nodes after
`ceo_review`, conditional on approval.

Concurrency notes: specialists run in a thread pool because each call is a
blocking LLM request. `Agent.run_logged` publishes events and reads the
`current_project_id` contextvar, which does NOT flow into pool threads by
itself -- each task is submitted via `contextvars.copy_context().run` so
per-agent events keep the correct project_id. Worker errors are captured
into the task's SwarmTaskResult (never raised): one failed specialist
should surface in validation, not abort the other five mid-flight.
"""

from __future__ import annotations

import contextvars
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from aio.agents.base import Agent
from aio.agents.parsing import json_response_instruction
from aio.models.swarm import SwarmPlan, SwarmTaskResult, SwarmValidation
from aio.orchestration.cancellation import MissionCancelled

logger = logging.getLogger("aio.orchestration.swarm")

# Modest cap: keeps sqlite execution-log writes from contending and keeps
# demo/anthropic rate usage predictable. Assignments beyond this simply
# queue inside the pool.
_MAX_PARALLEL_SPECIALISTS = 4

# Squad members the Queen may assign work to -- everyone except the two
# roles that already have graph nodes of their own.
_UNASSIGNABLE_ROLES = {"Queen Coordinator", "Production Validator"}


def assignable_roles(squad: dict[str, Agent]) -> dict[str, Agent]:
    return {role: agent for role, agent in squad.items() if role not in _UNASSIGNABLE_ROLES}


def plan_swarm(queen: Agent, goal: str, tech_plan: str, squad: dict[str, Agent]) -> SwarmPlan:
    roster = "\n".join(
        f"- {agent.role} ({agent.department})" for agent in assignable_roles(squad).values()
    )
    task = (
        f"Business goal:\n{goal}\n\n"
        f"Approved technical plan:\n{tech_plan}\n\n"
        f"Available specialists:\n{roster}\n\n"
        "Decompose the technical plan into 4 to 8 concrete task assignments "
        "for these specialists. Each assignment's `role` MUST be copied "
        "exactly from the roster above; each `task` must be a specific, "
        "self-contained instruction the specialist can execute alone.\n\n"
        + json_response_instruction(SwarmPlan)
    )
    plan = queen.run_logged_json(task, SwarmPlan, max_tokens=20000, handoff_target="Swarm")

    valid_roles = set(assignable_roles(squad))
    kept = [a for a in plan.assignments if a.role in valid_roles]
    for dropped in (a for a in plan.assignments if a.role not in valid_roles):
        logger.warning("queen assigned unknown role %r -- dropping assignment", dropped.role)
    return plan.model_copy(update={"assignments": kept})


def execute_swarm(squad: dict[str, Agent], plan: SwarmPlan) -> list[SwarmTaskResult]:
    def run_one(role: str, task: str) -> SwarmTaskResult:
        agent = squad[role]
        t0 = time.monotonic()
        try:
            output = agent.execute(task)
            return SwarmTaskResult(
                role=role, task=task, output=output, duration_seconds=time.monotonic() - t0
            )
        except MissionCancelled:
            # Unlike a genuine specialist failure (see module docstring:
            # captured into the result, never raised), a cancellation means
            # the operator stopped the whole mission -- it must propagate
            # past `f.result()` below so the rest of the graph stops too,
            # not get swallowed as if this one specialist merely failed.
            raise
        except Exception as exc:  # captured, not raised -- see module docstring
            logger.error("swarm specialist %r failed: %s", role, exc)
            return SwarmTaskResult(
                role=role, task=task, error=str(exc), duration_seconds=time.monotonic() - t0
            )

    with ThreadPoolExecutor(max_workers=_MAX_PARALLEL_SPECIALISTS) as pool:
        futures = [
            pool.submit(contextvars.copy_context().run, run_one, a.role, a.task)
            for a in plan.assignments
        ]
        return [f.result() for f in futures]


def validate_swarm(
    validator: Agent, goal: str, tech_plan: str, results: list[SwarmTaskResult]
) -> SwarmValidation:
    sections = []
    for r in results:
        body = f"ERROR: {r.error}" if r.error else r.output
        sections.append(f"### {r.role}\nTask: {r.task}\n\n{body}")
    task = (
        f"Business goal:\n{goal}\n\n"
        f"Approved technical plan:\n{tech_plan}\n\n"
        "Specialist outputs to validate:\n\n" + "\n\n".join(sections) + "\n\n"
        "Validate the combined output: does it cover the technical plan, "
        "are the pieces consistent with each other, and is anything "
        "missing or failed? List concrete issues; pass only if the swarm "
        "output is a sound basis for implementation.\n\n"
        + json_response_instruction(SwarmValidation)
    )
    return validator.run_logged_json(
        task, SwarmValidation, max_tokens=20000, handoff_target="Executive AI (CEO)"
    )
