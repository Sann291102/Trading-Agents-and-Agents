"""Observer platform. Importing this package registers the built-in eyes, so
`run_observation_cycle(business)` sees everything JARVIS ships with without
the caller knowing which module defines what -- the same import-for-side-effect
convention as `aio.connectors`.
"""

from aio.models.signals import ObserverStatus, Signal
from aio.observers.base import (
    Observer,
    all_observers,
    available_observers,
    get_observer,
    register_observer,
)
from aio.observers.cycle import run_observation_cycle
from aio.observers import builtin as _builtin  # noqa: F401 -- imported for registration

__all__ = [
    "Observer",
    "ObserverStatus",
    "Signal",
    "all_observers",
    "available_observers",
    "get_observer",
    "register_observer",
    "run_observation_cycle",
]
