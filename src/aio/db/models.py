from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, String, Text, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    """A single organizational-brain record of one Executive AI run.

    This is the long-term memory unit: one row per goal the organization
    was asked to execute, with the artifacts each department produced.

    `requirements` (plain text) has been superseded by
    `business_requirements_json` now that Product Manager output is a
    structured BusinessRequirementsDocument grounded in
    `research_report_json`. Both are stored as JSON text rather than
    normalized tables -- the full nested reports have no query pattern yet
    that would justify the extra schema complexity; revisit if/when one
    emerges (e.g. a dashboard querying individual research findings).
    """

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    goal: Mapped[str] = mapped_column(Text)
    research_report_json: Mapped[str] = mapped_column(Text, default="")
    research_review: Mapped[str] = mapped_column(Text, default="")
    research_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    business_requirements_json: Mapped[str] = mapped_column(Text, default="")
    tech_plan: Mapped[str] = mapped_column(Text, default="")
    review: Mapped[str] = mapped_column(Text, default="")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    # Engineering-swarm stage. Previously never persisted -- only visible on
    # the synchronous POST /projects response for the run that had just
    # finished. Now that POST /projects returns immediately and the mission
    # runs in the background (see api/main.py), that was the only window
    # these were ever visible in, so they're persisted here like every
    # other stage's output.
    swarm_plan_json: Mapped[str] = mapped_column(Text, default="")
    swarm_results_json: Mapped[str] = mapped_column(Text, default="")
    swarm_validation_json: Mapped[str] = mapped_column(Text, default="")
    preview_url: Mapped[str] = mapped_column(Text, default="")
    preview_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ExecutionLogRecord(Base):
    """One row per agent execution -- see observability/execution_log.py.

    This is the "future analytics" store the observability layer writes
    to: every agent call's timing, confidence, and outcome, queryable
    across the whole organization rather than scattered in log files.
    """

    __tablename__ = "execution_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_role: Mapped[str] = mapped_column(String)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning_summary: Mapped[str] = mapped_column(Text, default="")
    handoff_target: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ProjectEmbeddingRecord(Base):
    """Vector memory: one row per project embedding, for similarity search.

    Replaces the previous Qdrant backing (see memory/semantic.py). Vectors
    are stored as JSON text and compared with cosine similarity in NumPy at
    query time -- at this project's scale (one small vector per project) a
    brute-force scan is more than fast enough and needs no vector-DB server
    or extra dependency. `(collection, point_id)` is a composite primary key
    so multiple logical collections (e.g. per-test namespaces) can share one
    database without colliding, mirroring how Qdrant collections worked.
    """

    __tablename__ = "project_embeddings"

    collection: Mapped[str] = mapped_column(String, primary_key=True)
    point_id: Mapped[str] = mapped_column(String, primary_key=True)
    goal: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    vector_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MemoryEntryRecord(Base):
    """Organizational Memory Foundation -- see memory/service.py and
    models/memory.py. One row per MemoryEntry: a durable, addressable
    record of something the organization learned, decided, or produced,
    independent of the Project row that originated it.

    The Python attribute is `metadata_json`, not `metadata` -- SQLAlchemy's
    `DeclarativeBase` reserves `metadata` for its own table-metadata
    registry, so a mapped column can't use that name. Serialized as JSON
    text (matching `Project.research_report_json`'s existing pattern)
    rather than a normalized table, consistent with the same reasoning:
    no query pattern yet that needs individual metadata fields indexed.
    """

    __tablename__ = "memory_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(Text)
    department: Mapped[str] = mapped_column(String)
    owner: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class User(Base):
    """A signed-up operator. `password_hash` is a bcrypt hash (see
    auth/service.py) -- the plaintext password is never stored."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SessionToken(Base):
    """An opaque bearer token (see auth/service.py's `secrets.token_urlsafe`)
    issued on signup/login. No `default=_uuid` on `token` -- the token
    itself is always supplied explicitly by AuthService, unlike every other
    model's `id` column."""

    __tablename__ = "session_tokens"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
