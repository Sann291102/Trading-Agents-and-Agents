"""The observers JARVIS ships with.

Ordered by how much they need to work: `business_state` watches JARVIS's own
database and therefore runs on a fresh install with no configuration at all,
`website` needs only an outbound connection, and `github` is the template for
an observer gated behind a credential. Importing this module registers all
three; unavailable ones simply never run.
"""

from aio.observers.builtin.business_state import BusinessStateObserver
from aio.observers.builtin.github import GitHubObserver
from aio.observers.builtin.web import WebsiteObserver

__all__ = ["BusinessStateObserver", "GitHubObserver", "WebsiteObserver"]
