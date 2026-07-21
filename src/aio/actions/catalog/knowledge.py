"""JARVIS remembering, and recalling.

An operator that forgets is an operator that redoes work. These two actions
are how a finding, a decision, or a lesson stops being a line in a chat
transcript and becomes something the organization holds -- and how JARVIS
gets it back later.

Both declare `connector="memory"`, JARVIS's own always-available
organizational memory, so they read as capabilities in the connector panel
alongside the external integrations. The stores themselves arrive on the
ActionContext rather than being imported here: the API points them at the
same database as everything else in a run, and a context without them must
degrade to a clear FAILED result rather than crash the autonomous loop.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from aio.actions.base import ActionContext, ActionOutcome, ActionResult, ActionRisk
from aio.actions.registry import action
from aio.events.bus import OrgEvent, event_bus
from aio.models.memory import MemoryEntry, MemoryMetadata, MemoryType

_MEMORY_TYPES = tuple(member.value for member in MemoryType)


def _failed(summary: str, detail: str = "") -> ActionResult:
    return ActionResult(outcome=ActionOutcome.FAILED, summary=summary, detail=detail)


# -- save_memory_entry -------------------------------------------------------


class SaveMemoryEntryParams(BaseModel):
    title: str = Field(..., description="One line naming what is being remembered")
    summary: str = Field(..., description="The finding, decision, or lesson itself, in full")
    entry_type: str = Field(
        "lesson_learned",
        description=f"Kind of knowledge, one of: {', '.join(_MEMORY_TYPES)}",
    )
    department: str = Field("Executive Office", description="Department this belongs to")
    owner: str = Field("", description="Who produced it; defaults to whoever ran the action")
    confidence: float = Field(0.7, ge=0.0, le=1.0, description="How sure JARVIS is of it, 0-1")
    tags: list[str] = Field(default_factory=list, description="Tags to find it by later")


@action(
    "save_memory_entry",
    description="File a finding, decision, or lesson into organizational memory",
    risk=ActionRisk.SAFE,
    params_model=SaveMemoryEntryParams,
    owner_agent="Knowledge Manager",
    connector="memory",
)
def save_memory_entry(context: ActionContext, params: SaveMemoryEntryParams) -> ActionResult:
    if context.memory is None:
        return _failed(
            "Could not remember that -- organizational memory is not connected",
            "No MemoryService is attached to this run.",
        )

    title = params.title.strip()
    summary = params.summary.strip()
    if not title or not summary:
        return _failed("A memory entry needs both a title and a summary")

    raw_type = params.entry_type.strip().lower().replace(" ", "_").replace("-", "_")
    try:
        entry_type = MemoryType(raw_type)
    except ValueError:
        return _failed(
            f"{params.entry_type!r} is not a kind of memory JARVIS keeps",
            f"Valid types: {', '.join(_MEMORY_TYPES)}.",
        )

    entry = context.memory.create_entry(
        MemoryEntry(
            title=title,
            type=entry_type,
            summary=summary,
            department=params.department or "Executive Office",
            owner=params.owner.strip() or context.actor,
            confidence=params.confidence,
            metadata=MemoryMetadata(tags=params.tags, source_agent=context.actor),
        )
    )

    event_bus.publish(
        OrgEvent(
            type="knowledge_added",
            department=entry.department,
            agent_role=entry.owner,
            message=f"Filed to memory: {title}",
            payload={"entry_id": entry.id, "type": entry_type.value},
        )
    )
    return ActionResult(
        outcome=ActionOutcome.EXECUTED,
        summary=f"Filed to memory as a {entry_type.value.replace('_', ' ')}: {title}",
        detail=summary,
        data={"entry_id": entry.id, "type": entry_type.value},
    )


# -- search_memory -----------------------------------------------------------


class SearchMemoryParams(BaseModel):
    query: str = Field(..., description="What to look for, in plain language")
    top_k: int = Field(5, ge=1, le=20, description="How many matches to bring back")


@action(
    "search_memory",
    description="Search past work and findings in organizational memory",
    risk=ActionRisk.SAFE,
    params_model=SearchMemoryParams,
    owner_agent="Knowledge Manager",
    connector="memory",
)
def search_memory(context: ActionContext, params: SearchMemoryParams) -> ActionResult:
    if context.semantic is None:
        return _failed(
            "Could not search memory -- semantic memory is not connected",
            "No SemanticMemory is attached to this run.",
        )

    query = params.query.strip()
    if not query:
        return _failed("A memory search needs something to search for")

    matches = context.semantic.search_similar(query, params.top_k) or []
    if not matches:
        return ActionResult(
            outcome=ActionOutcome.EXECUTED,
            summary=f"Searched memory for '{query}' and found nothing on record",
            detail="Organizational memory has no prior work matching that.",
            data={"query": query, "matches": []},
        )

    # Rendered rather than returned raw: the detail is read by the founder in
    # the activity feed and fed back to the planner as context.
    lines = [
        f"{index}. {match.get('goal') or '(untitled)'}\n   {match.get('summary', '')}".rstrip()
        for index, match in enumerate(matches, start=1)
    ]
    return ActionResult(
        outcome=ActionOutcome.EXECUTED,
        summary=f"Searched memory for '{query}' and found {len(matches)} related item(s)",
        detail="\n".join(lines),
        data={"query": query, "matches": matches},
    )
