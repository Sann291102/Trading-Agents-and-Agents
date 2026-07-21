"""The fixed vocabulary of organizational events -- this is the contract
the frontend's live event stream is built against. Adding a new event kind
means adding a literal here (and a publish call wherever it happens); the
frontend switches on `event.type`, it never infers activity from anything
else.
"""

from __future__ import annotations

from typing import Literal

EventType = Literal[
    "agent_started",
    "agent_finished",
    "task_delegated",
    "research_complete",
    "review_requested",
    "approval_granted",
    "changes_requested",
    "memory_updated",
    "knowledge_added",
    "deployment_started",
    "deployment_finished",
    "workflow_failed",
    "workflow_cancelled",
    "os_started",
    "os_stopped",
    "living_market_state_updated",
    # JARVIS acting on its own: the autonomous loop and the action engine.
    "action_executed",
    "action_escalated",
    "action_failed",
    "autonomy_cycle",
]
