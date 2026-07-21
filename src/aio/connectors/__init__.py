"""Connector platform. Importing this package registers the built-ins, so
`connector_available("brave")` is answerable from anywhere without the caller
knowing which module defines it."""

from aio.connectors.base import (
    Capability,
    Connector,
    all_connectors,
    connector_available,
    get_connector,
    register_connector,
)
from aio.connectors import builtin as _builtin  # noqa: F401 -- imported for registration

__all__ = [
    "Capability",
    "Connector",
    "all_connectors",
    "connector_available",
    "get_connector",
    "register_connector",
]
