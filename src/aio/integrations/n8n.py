"""Thin client for triggering an n8n webhook when a JARVIS mission
completes -- lets an n8n workflow react (notify, file, sync to another
system) without any of that logic living in this codebase.

Deliberately one-directional and fire-and-forget: JARVIS calls out to n8n,
n8n does not call back into JARVIS. Gated behind `settings.n8n_base_url`:
empty (the default) makes `notify_mission_complete` a silent no-op, same
posture as Brave Search and Obsidian -- an integration the operator opts
into by configuring it, never a hard dependency of the core pipeline.
"""

from __future__ import annotations

import logging

import httpx

from aio.config import settings

logger = logging.getLogger("aio.integrations.n8n")


class N8nClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = (base_url if base_url is not None else settings.n8n_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.n8n_api_key

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    def notify_mission_complete(self, payload: dict) -> bool:
        """POSTs `payload` (project id, goal, approved/confidence summary)
        to the configured webhook path. Never raises -- a workflow-engine
        hiccup must not affect a mission that already completed and
        persisted."""
        if not self.enabled:
            return False
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = httpx.post(
                f"{self.base_url}{settings.n8n_mission_webhook_path}",
                json=payload,
                headers=headers,
                timeout=10.0,
            )
            response.raise_for_status()
            return True
        except Exception:
            logger.warning("n8n webhook call failed", exc_info=True)
            return False
