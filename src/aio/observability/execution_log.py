"""One record per agent execution -- the unit of organizational observability.

`Agent.run_logged` (see agents/base.py) produces one of these on every LLM
call: always logged via the standard `logging` module, and persisted to
long-term memory when an agent has one attached, so execution history is
queryable for analytics later (see LongTermMemory.list_execution_logs).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ExecutionMetrics:
    agent_role: str
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    confidence: float | None
    reasoning_summary: str
    handoff_target: str | None
    error: str | None = None
