"""Thin client for Obsidian's "Local REST API" community plugin
(https://github.com/coddingtonbear/obsidian-local-rest-api) -- lets JARVIS
write organizational memory straight into the operator's own vault as real
notes, instead of memory living only in the app's own database.

Requires that plugin to be installed and enabled in the target vault
(Settings -> Community plugins -> Local REST API; its settings tab shows
the API key and HTTPS port, 27124 by default). Gated behind
`settings.obsidian_api_key`: with no key configured, every write is a
silent, logged no-op -- JARVIS's local-DB memory (`MemoryService`) is
always the source of truth; Obsidian is a mirror, never a dependency.

The plugin serves HTTPS with a self-signed certificate (it's a purely
local, same-machine API), so certificate verification is intentionally
disabled here -- there is no real MITM surface on 127.0.0.1.
"""

from __future__ import annotations

import logging

import httpx

from aio.config import settings

logger = logging.getLogger("aio.integrations.obsidian")


class ObsidianClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = (base_url if base_url is not None else settings.obsidian_api_url).rstrip(
            "/"
        )
        self.api_key = api_key if api_key is not None else settings.obsidian_api_key

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def write_note(self, vault_path: str, content: str) -> bool:
        """Creates or overwrites the note at `vault_path` (e.g.
        "JARVIS/research_finding/<id>.md") with `content`. Returns whether
        the write succeeded; never raises -- a vault sync failure must
        never take down the mission that already persisted to the local
        database."""
        if not self.enabled:
            return False
        try:
            response = httpx.put(
                f"{self.base_url}/vault/{vault_path}",
                content=content.encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "text/markdown",
                },
                timeout=10.0,
                verify=False,
            )
            response.raise_for_status()
            return True
        except Exception:
            logger.warning("Obsidian write failed for %r", vault_path, exc_info=True)
            return False
