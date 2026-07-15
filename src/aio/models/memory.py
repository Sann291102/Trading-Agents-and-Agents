"""Organizational Memory Foundation -- typed contracts only.

This is deliberately narrow: a `MemoryEntry` is a durable, addressable
record of something the organization learned, decided, or produced (a
research finding, an architectural decision, a lesson learned, a reusable
component, a risk worth remembering across projects), independent of the
`Project` row that originated it -- one project can eventually spawn
several memory entries.

Retrieval (semantic search, filtering by relevance), a knowledge graph
linking entries together, and any UI are explicitly out of scope for this
foundation -- see MemoryService's docstring and ARCHITECTURE.md's roadmap
for where those build on top of this module later.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """The kinds of memory the organization currently produces. Extend
    this enum as new departments/agents produce new kinds of durable
    knowledge (e.g. a future QA department might add TEST_FINDING) --
    existing entries/rows are unaffected by adding a new member."""

    RESEARCH_FINDING = "research_finding"
    ARCHITECTURAL_DECISION = "architectural_decision"
    LESSON_LEARNED = "lesson_learned"
    REUSABLE_COMPONENT = "reusable_component"
    RISK = "risk"


class MemoryMetadata(BaseModel):
    """Free-form, forward-compatible extras that don't warrant their own
    top-level `MemoryEntry` column. `extra` exists so a future feature can
    attach structured data without a schema migration; anything that
    becomes a first-class query need should graduate to a real column
    instead of living in `extra` indefinitely."""

    tags: list[str] = Field(default_factory=list)
    source_agent: str | None = None
    references: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class MemoryEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str | None = None
    title: str
    type: MemoryType
    summary: str
    department: str
    owner: str
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: MemoryMetadata = Field(default_factory=MemoryMetadata)
