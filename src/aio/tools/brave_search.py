"""Thin client for Brave Search's Web Search API
(https://api.search.brave.com) -- a real web-search tool JARVIS's Research &
Planning specialists can use to ground findings in current information
instead of relying only on model-knowledge recall.

Gated behind `settings.brave_api_key`: with no key configured, `search()`
returns an empty list and every call site degrades to exactly the
model-knowledge-only behavior this codebase had before Brave was wired in --
see `agents/research_tools.py::web_research_context`, the one place that
matters for callers.
"""

from __future__ import annotations

import logging

import httpx

from aio.config import settings

logger = logging.getLogger("aio.tools.brave_search")


class BraveSearchClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.brave_api_key

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, count: int = 5) -> list[dict]:
        """Returns up to `count` results as {"title", "url", "snippet"}
        dicts, or [] if unconfigured or the request fails. Research must
        never block on Brave being down or rate-limited -- this is an
        enrichment on top of the LLM's own knowledge, never a hard
        dependency, so every failure mode here is a silent, logged no-op."""
        if not self.enabled:
            return []
        try:
            response = httpx.get(
                settings.brave_search_base_url,
                params={"q": query, "count": count},
                headers={"Accept": "application/json", "X-Subscription-Token": self.api_key},
                timeout=10.0,
            )
            response.raise_for_status()
            results = response.json().get("web", {}).get("results", [])
        except Exception:
            logger.warning("Brave Search request failed for query %r", query, exc_info=True)
            return []
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
            }
            for item in results[:count]
        ]
