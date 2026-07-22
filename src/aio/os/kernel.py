"""The OS kernel: the clock that keeps JARVIS running between conversations.

This used to poll a mock option chain and update a market digital twin. That
direction is abandoned -- JARVIS is a founder's Executive Business OS, not a
trading terminal -- so the loop now drives the autonomous executive cycle in
`aio.os.autonomy` instead. The class name, the module singleton, and the
start/stop method names are kept verbatim because `api/main.py`'s lifespan
already calls them; renaming them would break startup for no gain.

The kernel deliberately knows almost nothing. It owns scheduling and the
founder's throttle (`AutonomySettings`); the judgement lives in
`aio.os.autonomy`, and its dependencies arrive through `configure()` rather
than by importing app state, so a cycle can be driven in a test without
standing up FastAPI.

There are two clocks, not one, because watching and thinking cost different
things. Observation is a few reads and no model call, so it runs often;
reasoning costs an LLM call per cycle, so it runs rarely. Splitting them is
what lets JARVIS notice something within minutes while still thinking at
whatever pace the founder is willing to pay for.

Two constraints shape both loops:
  - A cycle does blocking work (SQLite + a synchronous LLM call), so it runs
    in a worker thread via `asyncio.to_thread`. Running it inline would stall
    the event loop serving the SSE stream, freezing the founder's live feed
    for the length of an LLM call.
  - Nothing may kill the loop. A failed cycle is reported and the loop sleeps
    on to the next one; a process that silently stops operating the company
    is worse than one that logs a bad cycle.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from aio.events.bus import OrgEvent, event_bus
from aio.models.autonomy import AutonomySettings
from aio.os.autonomy import run_cycle

from aio.actions.base import ActionResult

if TYPE_CHECKING:
    from aio.actions.base import ActionContext
    from aio.business.service import BusinessService
    from aio.models.signals import Signal

logger = logging.getLogger("aio.os.kernel")


class ExecutiveBrain:
    """Owns the autonomous cycle's schedule, settings, and lifecycle."""

    def __init__(self) -> None:
        # Disabled by default: JARVIS must not act on a fresh install until
        # the founder switches autonomy on.
        self._settings = AutonomySettings()
        self._business_factory: Callable[[], "BusinessService"] | None = None
        self._context_factory: Callable[[], "ActionContext"] | None = None
        self._background_tasks: list[asyncio.Task] = []
        self._is_running = False
        self._cycles_run = 0
        self._observations_run = 0
        # Two clocks plus two "do it now" endpoints all dispatch into worker
        # threads, so kernel-driven work would otherwise overlap. Recording a
        # signal is a read-modify-write (find the open row for this dedupe
        # key, else insert) with no unique constraint behind it, so two sweeps
        # in flight at once write two rows for one condition and the dedupe
        # invariant -- the thing that keeps a standing problem from burying
        # the feed -- silently stops holding. Reentrant so a future caller
        # that nests observing inside a cycle blocks nothing.
        self._work_lock = threading.RLock()

    # -- wiring -----------------------------------------------------------

    def configure(
        self,
        business_factory: Callable[[], "BusinessService"],
        context_factory: Callable[[], "ActionContext"],
    ) -> None:
        """Inject where the business state and action authority come from.

        Factories rather than instances: each cycle runs on a fresh worker
        thread, and a SQLAlchemy session bound to a different thread must not
        be reused across them.
        """
        self._business_factory = business_factory
        self._context_factory = context_factory

    @property
    def is_configured(self) -> bool:
        return self._business_factory is not None and self._context_factory is not None

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def cycles_run(self) -> int:
        return self._cycles_run

    @property
    def observations_run(self) -> int:
        return self._observations_run

    # -- settings ---------------------------------------------------------

    def get_settings(self) -> AutonomySettings:
        """A copy -- callers must go through `update_settings` so bounds are
        always re-validated."""
        return self._settings.model_copy()

    def observe_interval_seconds(self) -> int:
        """How often to look, which is not how often to think.

        Read off the settings model with `getattr` rather than as an
        attribute: the kernel owns startup, and a settings model that predates
        this field must degrade to watching on the reasoning clock instead of
        taking the whole API down with an AttributeError.
        """
        interval = getattr(self._settings, "observe_interval_seconds", None)
        if not isinstance(interval, int) or interval < 1:
            return self._settings.interval_seconds
        return interval

    def update_settings(
        self, changes: "AutonomySettings | dict[str, Any] | None" = None, **kwargs: Any
    ) -> AutonomySettings:
        """Apply a partial update, re-validating the whole model so an
        out-of-range interval is rejected rather than stored.

        Takes a model, a dict, or keyword arguments because the founder's
        toggle, an HTTP payload, and a test all want different shapes.
        """
        data = (
            changes.model_dump()
            if isinstance(changes, AutonomySettings)
            else dict(changes or {})
        )
        data.update(kwargs)
        was_enabled = self._settings.enabled
        self._settings = AutonomySettings.model_validate({**self._settings.model_dump(), **data})

        if self._settings.enabled != was_enabled:
            # The founder handing over (or taking back) authority is the most
            # consequential toggle in the product -- it belongs in the feed.
            message = (
                f"Autonomy on -- JARVIS will act every {self._settings.interval_seconds}s, "
                f"up to {self._settings.max_actions_per_cycle} action(s) per cycle."
                if self._settings.enabled
                else "Autonomy off -- JARVIS will not act on its own."
            )
            event_bus.publish(
                OrgEvent(type="autonomy_cycle", agent_role="JARVIS", message=message)
            )
        return self.get_settings()

    # -- lifecycle (names fixed by api/main.py's lifespan) -----------------

    def start_background_intelligence(self) -> None:
        if self._is_running:
            return
        try:
            tasks = [
                asyncio.create_task(self._autonomy_loop()),
                asyncio.create_task(self._observation_loop()),
            ]
        except RuntimeError:
            # No running loop (imported by a script or a sync test). The
            # kernel stays usable via run_once()/observe_once(); it just has
            # no clock.
            logger.warning("no running event loop -- autonomy loop not started")
            return
        self._is_running = True
        self._background_tasks.extend(tasks)
        event_bus.publish(
            OrgEvent(
                type="os_started",
                agent_role="JARVIS",
                message="Executive Brain online -- autonomous cycle scheduled.",
                payload={
                    **self._settings.model_dump(),
                    "observe_interval_seconds": self.observe_interval_seconds(),
                },
            )
        )

    def stop_background_intelligence(self) -> None:
        self._is_running = False
        for task in self._background_tasks:
            task.cancel()
        self._background_tasks.clear()
        event_bus.publish(
            OrgEvent(
                type="os_stopped",
                agent_role="JARVIS",
                message="Executive Brain offline -- autonomous cycle stopped.",
            )
        )

    # -- the loop ---------------------------------------------------------

    async def _autonomy_loop(self) -> None:
        while self._is_running:
            # Sleep first: startup must never trigger an immediate burst of
            # actions before the founder has even loaded the dashboard.
            await asyncio.sleep(max(1, self._settings.interval_seconds))
            if not self._is_running or not self._settings.enabled:
                continue
            try:
                await asyncio.to_thread(self._run_cycle_blocking)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # `action_failed` rather than an invented event type -- the
                # frontend switches on the literals in events/types.py.
                logger.exception("autonomy cycle failed")
                event_bus.publish(
                    OrgEvent(
                        type="action_failed",
                        agent_role="JARVIS",
                        message=f"Autonomy cycle failed: {exc}",
                        payload={"error": str(exc)},
                    )
                )

    async def _observation_loop(self) -> None:
        """The cheap clock. Same shape as the autonomy loop, no LLM call.

        Gated on `enabled` like the reasoning loop: observing is passive, but
        it writes rows and fills the founder's feed, and "autonomy off" has to
        mean JARVIS does nothing unprompted.
        """
        while self._is_running:
            await asyncio.sleep(max(1, self.observe_interval_seconds()))
            if not self._is_running or not self._settings.enabled:
                continue
            try:
                await asyncio.to_thread(self._observe_blocking)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("observation cycle failed")
                event_bus.publish(
                    OrgEvent(
                        type="action_failed",
                        agent_role="JARVIS",
                        message=f"Observation cycle failed: {exc}",
                        payload={"error": str(exc)},
                    )
                )

    def run_once(self, *, observe: bool = True) -> list[ActionResult]:
        """Run one cycle immediately, ignoring `enabled` -- this is the
        founder asking for it explicitly, not JARVIS acting on its own.

        Returns what the cycle actually did so a "run now" request can show
        it. Blocking: call it from a worker thread, never the event loop.
        """
        return self._run_cycle_blocking(observe=observe)

    def observe_once(self) -> list["Signal"]:
        """Look now, without thinking: one observation sweep, no LLM call.

        Exists so the product can offer a "check on things" that costs
        nothing, and so a founder with autonomy switched off can still ask
        what JARVIS can see. Returns the newly-observed signals. Blocking.
        """
        return self._observe_blocking()

    def _run_cycle_blocking(self, *, observe: bool = True) -> list[ActionResult]:
        if self._business_factory is None or self._context_factory is None:
            logger.warning("autonomy cycle skipped -- kernel not configured")
            return []
        # Observes again even though the cheap loop may have looked recently:
        # a plan should be made against the world as of now, not as of up to
        # one observation interval ago.
        with self._work_lock:
            results = run_cycle(
                self._business_factory(),
                context_factory=self._context_factory,
                limit=self._settings.max_actions_per_cycle,
                observe=observe,
            )
            self._cycles_run += 1
        return results

    def _observe_blocking(self) -> list["Signal"]:
        if self._business_factory is None:
            logger.warning("observation skipped -- kernel not configured")
            return []
        try:
            from aio.observers.cycle import run_observation_cycle
        except ImportError:
            # The kernel must boot on an install without the observers
            # package; it simply has nothing to watch with.
            logger.warning("observers unavailable -- nothing to watch")
            return []
        # Waits rather than skips: a sweep is short, and a dropped one is a
        # window in which JARVIS is not watching.
        with self._work_lock:
            signals = run_observation_cycle(self._business_factory())
            self._observations_run += 1
        return signals


# Module-level singleton: api/main.py's lifespan reaches the kernel through
# get_kernel(), and there is exactly one clock per process.
_kernel = ExecutiveBrain()


def get_kernel() -> ExecutiveBrain:
    return _kernel
