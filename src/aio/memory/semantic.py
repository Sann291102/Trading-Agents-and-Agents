"""Vector memory for similarity search over past projects.

Backed by the same SQLAlchemy database as the rest of the organizational
memory (SQLite locally, Postgres in a server deployment) -- no vector-DB
server, no extra service, no network. Each project's embedding is stored as
a JSON vector on a `project_embeddings` row (see db/models.py); similarity
search loads the collection's vectors and ranks them by cosine similarity in
NumPy at query time. At this project's scale (one small vector per project)
a brute-force scan is trivially fast, and it keeps the whole stack runnable
from a single local database file.

Embeddings are pluggable via the `embed_fn` constructor argument so this can
be swapped to a real embeddings provider (e.g. Voyage AI, which Anthropic
recommends since Claude does not serve embeddings directly) without touching
callers. The default embedder is a deterministic hashing-trick bag-of-words
vector: zero API cost, no extra dependencies, keeps this slice runnable
offline -- but it is a placeholder, not a real semantic embedding. Replace
`default_hashing_embedder` before relying on this for production-quality
retrieval.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable

import numpy as np
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from aio.config import settings
from aio.db.models import Base, ProjectEmbeddingRecord
from aio.events.bus import OrgEvent, event_bus

EmbedFn = Callable[[str], list[float]]

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_DIM = 256


def default_hashing_embedder(text: str, dim: int = _DIM) -> list[float]:
    vector = [0.0] * dim
    for token in _TOKEN_RE.findall(text.lower()):
        idx = int(hashlib.md5(token.encode()).hexdigest(), 16) % dim
        vector[idx] += 1.0
    norm = sum(v * v for v in vector) ** 0.5
    if norm > 0:
        vector = [v / norm for v in vector]
    return vector


class SemanticMemory:
    def __init__(
        self,
        database_url: str | None = None,
        location: str | None = None,
        collection: str | None = None,
        embed_fn: EmbedFn = default_hashing_embedder,
        dim: int = _DIM,
    ) -> None:
        resolved_url = self._resolve_url(database_url, location)
        if resolved_url == "sqlite://":
            # Shared in-memory DB (used by tests and cost-free local runs):
            # StaticPool + a single connection so every session sees the same
            # in-memory data instead of a fresh empty DB per connection.
            self._engine = create_engine(
                resolved_url,
                future=True,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            self._engine = create_engine(resolved_url, future=True)
        self._Session: sessionmaker[Session] = sessionmaker(bind=self._engine, future=True)
        # A logical namespace within the DB (mirrors a Qdrant "collection"),
        # so multiple independent stores can share one database file.
        self._collection = collection or settings.semantic_collection
        self._embed_fn = embed_fn
        self._dim = dim

    @staticmethod
    def _resolve_url(database_url: str | None, location: str | None) -> str:
        if database_url is not None:
            return database_url
        if location is not None:
            # Backwards-compatible with the former Qdrant kwarg: ":memory:"
            # -> shared in-memory SQLite; any other value -> a SQLite file.
            return "sqlite://" if location == ":memory:" else f"sqlite:///{location}"
        return settings.database_url

    def init_collection(self) -> None:
        # Idempotent; only adds the project_embeddings table if missing.
        Base.metadata.create_all(self._engine)

    def upsert_project(self, project_id: str, goal: str, summary: str) -> None:
        vector = self._embed_fn(f"{goal}\n{summary}")
        with self._Session() as session:
            session.merge(
                ProjectEmbeddingRecord(
                    collection=self._collection,
                    point_id=project_id,
                    goal=goal,
                    summary=summary,
                    vector_json=json.dumps(vector),
                )
            )
            session.commit()
        event_bus.publish(
            OrgEvent(
                type="knowledge_added",
                department="Research",
                project_id=project_id,
                message="Research embedded into organizational (semantic) memory",
            )
        )

    def search_similar(self, query: str, top_k: int = 5) -> list[dict]:
        query_vec = np.asarray(self._embed_fn(query), dtype=float)
        query_norm = float(np.linalg.norm(query_vec))
        with self._Session() as session:
            rows = list(
                session.scalars(
                    select(ProjectEmbeddingRecord).where(
                        ProjectEmbeddingRecord.collection == self._collection
                    )
                )
            )
        scored: list[tuple[float, ProjectEmbeddingRecord]] = []
        for row in rows:
            vector = np.asarray(json.loads(row.vector_json), dtype=float)
            denom = query_norm * float(np.linalg.norm(vector))
            score = float(query_vec @ vector / denom) if denom else 0.0
            scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {"id": row.point_id, "score": score, "goal": row.goal, "summary": row.summary}
            for score, row in scored[:top_k]
        ]
