"""Every capability JARVIS has, pulled in for its registration side effect.

Actions register themselves when their module is imported, so importing this
package *is* how the catalog gets populated -- `aio.actions` and the API's
`_load_action_catalog()` both do exactly that. A new capability module only
has to be listed here to exist everywhere: the planner's menu, `/actions`,
and the approval-execution path all read the same registry.
"""

from __future__ import annotations

from aio.actions.catalog import business_ops as business_ops  # noqa: F401
from aio.actions.catalog import delegation as delegation  # noqa: F401
from aio.actions.catalog import knowledge as knowledge  # noqa: F401

__all__ = ["business_ops", "delegation", "knowledge"]
