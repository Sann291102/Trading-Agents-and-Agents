"""Organizational Memory Foundation -- storage layer.

`MemoryService` is the single place responsible for all memory operations
on `MemoryEntry` records. It is deliberately CRUD-only: create, get by id,
list recent entries. No search/relevance ranking, no filtering by
department/type/project (that starts to be "retrieval", which along with
a knowledge graph and any UI is explicitly out of scope for this
foundation -- see ARCHITECTURE.md's roadmap for what layers on top of this
module later, and `aio.memory.semantic.SemanticMemory` for the existing,
separate vector-similarity search over *projects* that already exists
today and is not affected by this module).

Mirrors `LongTermMemory`'s constructor/session pattern for consistency:
its own SQLAlchemy engine against the same `Base`/database, not a shared
connection pool object passed around.
"""

from __future__ import annotations

from datetime import timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from aio.config import settings
from aio.db.models import Base, MemoryEntryRecord
from aio.models.memory import MemoryEntry, MemoryMetadata, MemoryType


class MemoryService:
    def __init__(self, database_url: str | None = None) -> None:
        self._engine = create_engine(database_url or settings.database_url, future=True)
        self._Session: sessionmaker[Session] = sessionmaker(bind=self._engine, future=True)

    def init_schema(self) -> None:
        Base.metadata.create_all(self._engine)

    def create_entry(self, entry: MemoryEntry) -> MemoryEntry:
        with self._Session() as session:
            record = MemoryEntryRecord(
                id=entry.id,
                project_id=entry.project_id,
                title=entry.title,
                type=entry.type.value,
                summary=entry.summary,
                department=entry.department,
                owner=entry.owner,
                confidence=entry.confidence,
                created_at=entry.created_at,
                metadata_json=entry.metadata.model_dump_json(),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return _to_memory_entry(record)

    def get_entry(self, entry_id: str) -> MemoryEntry | None:
        with self._Session() as session:
            record = session.get(MemoryEntryRecord, entry_id)
            return _to_memory_entry(record) if record is not None else None

    def list_entries(self, limit: int = 50) -> list[MemoryEntry]:
        with self._Session() as session:
            stmt = (
                select(MemoryEntryRecord)
                .order_by(MemoryEntryRecord.created_at.desc())
                .limit(limit)
            )
            return [_to_memory_entry(record) for record in session.scalars(stmt)]


def _to_memory_entry(record: MemoryEntryRecord) -> MemoryEntry:
    created_at = record.created_at
    if created_at.tzinfo is None:
        # SQLite has no native tz-aware datetime type and silently drops
        # tzinfo on round-trip (unlike Postgres); every value written here
        # is always UTC (see MemoryEntry.created_at's default), so a naive
        # read-back is unambiguously UTC, not a genuinely tz-less instant.
        created_at = created_at.replace(tzinfo=timezone.utc)
    return MemoryEntry(
        id=record.id,
        project_id=record.project_id,
        title=record.title,
        type=MemoryType(record.type),
        summary=record.summary,
        department=record.department,
        owner=record.owner,
        confidence=record.confidence,
        created_at=created_at,
        metadata=MemoryMetadata.model_validate_json(record.metadata_json),
    )
