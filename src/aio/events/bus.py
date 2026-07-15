"""In-process pub/sub broadcaster for organizational events.

Single-process only (no Redis) -- correct for this vertical slice's
single-instance deployment; horizontal scaling (multiple API replicas
sharing one event stream) is a documented roadmap item, not something
stubbed out here with no backing implementation behind it.

`publish()` is called from arbitrary synchronous code deep inside
`Agent._log`, orchestration graph nodes, and memory writes -- code that
runs on a worker thread, since FastAPI executes sync `def` path operations
via a thread pool (`anyio.to_thread`), while SSE subscribers `await
queue.get()` on the event loop thread. `asyncio.Queue` is not safe to touch
across threads, so every publish is marshalled onto the bound event loop
via `call_soon_threadsafe`, and the subscriber set / history list are
guarded by a plain `threading.Lock` (not `asyncio.Lock`, which only
protects against other coroutines on the *same* loop, not real OS threads).
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .types import EventType


class OrgEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: EventType
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    department: str | None = None
    agent_role: str | None = None
    project_id: str | None = None
    confidence: float | None = None
    duration_seconds: float | None = None
    message: str
    payload: dict = Field(default_factory=dict)


class EventBus:
    def __init__(self, history_limit: int = 300) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._listeners: list[Callable[[OrgEvent], None]] = []
        self._history: list[OrgEvent] = []
        self._history_limit = history_limit
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def add_listener(self, fn: Callable[[OrgEvent], None]) -> None:
        """Register a plain synchronous callback invoked inline, in-process,
        on every publish() -- on whatever thread called publish(). This is
        for cheap, always-in-memory consumers like AgentStatusTracker that
        need to observe every event without going through the async
        SSE-subscriber queue machinery (which requires a running event
        loop). Callbacks must not block or raise."""
        with self._lock:
            self._listeners.append(fn)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Call once, from the running loop, at API startup (see
        api/main.py's lifespan). Until bound, publish() falls back to a
        direct same-thread put -- fine for scripts/tests with no live SSE
        subscribers anyway."""
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(queue)

    def publish(self, event: OrgEvent) -> None:
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._history_limit:
                del self._history[: len(self._history) - self._history_limit]
            subscribers = list(self._subscribers)
            listeners = list(self._listeners)

        for listener in listeners:
            listener(event)

        for queue in subscribers:
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._put_nowait_safe, queue, event)
            else:
                self._put_nowait_safe(queue, event)

    @staticmethod
    def _put_nowait_safe(queue: asyncio.Queue, event: OrgEvent) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # A slow/stalled subscriber must not block or crash the
            # publisher -- drop the oldest queued event to make room.
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def recent(self, limit: int = 50) -> list[OrgEvent]:
        with self._lock:
            return list(self._history[-limit:])


event_bus = EventBus()
