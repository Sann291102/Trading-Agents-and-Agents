"""Schemas for the Engineering Swarm stage.

The swarm is the second half of the organization: after the Executive
approves the tech plan, the Queen Coordinator decomposes it into concrete
task assignments for the ruflo specialist agents (see
aio/agents/ruflo_defs/), the assigned specialists execute in parallel, and
the Production Validator gates the combined output. These models are the
contracts between those three steps.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SwarmAssignment(BaseModel):
    role: str
    task: str
    rationale: str = ""


class SwarmPlan(BaseModel):
    """Queen Coordinator's decomposition of the approved tech plan."""

    assignments: list[SwarmAssignment]
    strategy: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
    reasoning_summary: str = ""


class SwarmTaskResult(BaseModel):
    role: str
    task: str
    output: str = ""
    duration_seconds: float | None = None
    error: str | None = None


class SwarmValidation(BaseModel):
    """Production Validator's verdict over the combined swarm output."""

    passed: bool
    issues: list[str] = []
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
    reasoning_summary: str = ""
