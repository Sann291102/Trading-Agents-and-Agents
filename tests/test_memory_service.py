"""Organizational Memory Foundation tests -- models + MemoryService CRUD.

Deliberately does not test search/filtering/ranking: this foundation is
CRUD-only by design (see memory/service.py's module docstring)."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from aio.memory.service import MemoryService
from aio.models.memory import MemoryEntry, MemoryMetadata, MemoryType


def _entry(**overrides) -> MemoryEntry:
    defaults = dict(
        project_id="proj-1",
        title="Clinic scheduling is a viable niche",
        type=MemoryType.RESEARCH_FINDING,
        summary="Underserved segment identified with a clear differentiation window.",
        department="Research",
        owner="Research Coordinator",
        confidence=0.78,
        metadata=MemoryMetadata(
            tags=["healthcare", "scheduling"],
            source_agent="Research Coordinator",
        ),
    )
    defaults.update(overrides)
    return MemoryEntry(**defaults)


def test_memory_entry_requires_confidence_between_zero_and_one():
    with pytest.raises(ValidationError):
        _entry(confidence=1.5)
    with pytest.raises(ValidationError):
        _entry(confidence=-0.1)


def test_memory_entry_defaults_id_created_at_and_metadata():
    entry = MemoryEntry(
        title="Prefer modular monolith for first release",
        type=MemoryType.ARCHITECTURAL_DECISION,
        summary="Avoids premature microservice complexity.",
        department="Engineering",
        owner="Backend Lead",
        confidence=0.8,
    )
    assert entry.id
    assert entry.created_at.tzinfo is not None
    assert entry.metadata == MemoryMetadata()
    assert entry.project_id is None


def test_memory_entry_round_trips_through_json():
    entry = _entry()
    rehydrated = MemoryEntry.model_validate_json(entry.model_dump_json())
    assert rehydrated == entry


def _service(tmp_path) -> MemoryService:
    db_url = f"sqlite:///{tmp_path}/test.db"
    service = MemoryService(database_url=db_url)
    service.init_schema()
    return service


def test_create_entry_persists_and_round_trips(tmp_path):
    service = _service(tmp_path)
    entry = _entry()

    created = service.create_entry(entry)

    assert created == entry


def test_get_entry_returns_persisted_entry(tmp_path):
    service = _service(tmp_path)
    entry = _entry()
    service.create_entry(entry)

    fetched = service.get_entry(entry.id)

    assert fetched == entry


def test_get_entry_returns_none_for_missing_id(tmp_path):
    service = _service(tmp_path)

    assert service.get_entry("does-not-exist") is None


def test_list_entries_orders_most_recent_first(tmp_path):
    service = _service(tmp_path)
    older = _entry(
        title="older finding",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    newer = _entry(
        title="newer finding",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    service.create_entry(older)
    service.create_entry(newer)

    entries = service.list_entries()

    assert [e.title for e in entries] == ["newer finding", "older finding"]


def test_list_entries_respects_limit(tmp_path):
    service = _service(tmp_path)
    for i in range(5):
        service.create_entry(_entry(title=f"finding-{i}"))

    entries = service.list_entries(limit=2)

    assert len(entries) == 2


def test_create_entry_preserves_metadata_extra_and_references(tmp_path):
    service = _service(tmp_path)
    entry = _entry(
        metadata=MemoryMetadata(
            tags=["risk"],
            source_agent="Product Manager",
            references=["other-entry-id"],
            extra={"severity": "high"},
        )
    )

    fetched = service.get_entry(service.create_entry(entry).id)

    assert fetched.metadata.references == ["other-entry-id"]
    assert fetched.metadata.extra == {"severity": "high"}


def test_create_entry_without_project_id_is_allowed(tmp_path):
    service = _service(tmp_path)
    entry = _entry(project_id=None)

    created = service.create_entry(entry)

    assert created.project_id is None
    assert service.get_entry(created.id).project_id is None
