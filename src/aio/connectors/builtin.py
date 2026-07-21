"""The connectors JARVIS ships with.

Each one is a thin declaration over an integration that already exists in this
codebase -- the HTTP/transport logic stays in `aio.integrations.*` and
`aio.tools.*`; this module only answers "is it configured, and what does it let
JARVIS do". `client()` hands back a freshly constructed client on every call so
a key added via `settings.reload()` takes effect without a restart.

The external three are opt-in and report themselves unavailable until keyed;
`memory` is JARVIS's own organizational memory, so it is always on -- an action
that files a decision to memory must never be filtered out of the planner's
menu for lack of configuration.
"""

from __future__ import annotations

from aio.config import settings
from aio.connectors.base import Capability, Connector, register_connector


class ObsidianConnector(Connector):
    """The founder's own vault, via the Local REST API community plugin --
    where JARVIS's memory becomes notes the founder can read without JARVIS."""

    name = "obsidian"
    display_name = "Obsidian"
    description = "Read and write notes in your Obsidian vault."
    capabilities = (Capability.READ, Capability.WRITE)
    setup_hint = (
        "Set OBSIDIAN_API_KEY in .env (Obsidian -> Settings -> Community plugins -> "
        "Local REST API shows the key), and OBSIDIAN_API_URL if the plugin is not on "
        "the default https://127.0.0.1:27124."
    )

    def available(self) -> bool:
        return bool(settings.obsidian_api_key)

    def client(self):
        from aio.integrations.obsidian import ObsidianClient

        return ObsidianClient()


class N8nConnector(Connector):
    """The founder's workflow engine: JARVIS triggers workflows, n8n owns the
    fan-out to whatever else they have wired up."""

    name = "n8n"
    display_name = "n8n"
    description = "Trigger n8n workflows to act on other systems."
    capabilities = (Capability.EXECUTE,)
    setup_hint = (
        "Set N8N_BASE_URL in .env to your n8n instance (e.g. http://localhost:5678), "
        "plus N8N_API_KEY if that instance requires auth."
    )

    def available(self) -> bool:
        # Keyed on the base URL, not the API key: a locally hosted n8n commonly
        # runs unauthenticated, and N8nClient itself only sends auth if a key
        # is present.
        return bool(settings.n8n_base_url)

    def client(self):
        from aio.integrations.n8n import N8nClient

        return N8nClient()


class BraveConnector(Connector):
    """Live web search -- how JARVIS grounds competitive and market work in
    current information rather than model recall."""

    name = "brave"
    display_name = "Brave Search"
    description = "Search the live web for current information."
    capabilities = (Capability.READ,)
    setup_hint = "Set BRAVE_API_KEY in .env (free tier at https://api.search.brave.com)."

    def available(self) -> bool:
        return bool(settings.brave_api_key)

    def client(self):
        from aio.tools.brave_search import BraveSearchClient

        return BraveSearchClient()


class MemoryConnector(Connector):
    """JARVIS's own organizational memory. Internal, so always available --
    handlers reach it through `ActionContext.memory` rather than a client
    built here, which keeps memory writes inside the executor's audit trail."""

    name = "memory"
    display_name = "Organizational Memory"
    description = "Store and recall what the company has learned and decided."
    capabilities = (Capability.READ, Capability.WRITE)

    def available(self) -> bool:
        return True


register_connector(ObsidianConnector())
register_connector(N8nConnector())
register_connector(BraveConnector())
register_connector(MemoryConnector())
