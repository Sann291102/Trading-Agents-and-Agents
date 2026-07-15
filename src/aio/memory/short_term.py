"""In-process working memory for a single orchestration run.

Scoped to one project/session. Not persisted -- once a run finishes, its
durable outputs are written to LongTermMemory (facts) and SemanticMemory
(embeddings) by the orchestration graph. This class only exists to pass
accumulating context between agents within one run without re-sending the
full history to every LLM call.
"""

from __future__ import annotations


class ShortTermMemory:
    def __init__(self) -> None:
        self._context: dict[str, object] = {}

    def set(self, key: str, value: object) -> None:
        self._context[key] = value

    def get(self, key: str, default: object | None = None) -> object | None:
        return self._context.get(key, default)

    def as_dict(self) -> dict[str, object]:
        return dict(self._context)
