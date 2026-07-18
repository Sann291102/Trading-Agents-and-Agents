"""Shared helper letting the four Research & Planning specialists ground
their reports in real web results via Brave Search, instead of
model-knowledge-only recall.

Additive by construction: with no `BRAVE_API_KEY` configured,
`web_research_context` returns an empty string and every research agent's
task prompt is byte-identical to what it was before Brave existed. This is
the one seam all four agents call through, so research becomes part of
JARVIS's long-term intelligence the same way for all of them -- the
resulting snippets flow into each specialist's structured report, which
already gets persisted as organizational memory (see
`memory/recording.py`), rather than being a one-off lookup that's forgotten
after the call.
"""

from __future__ import annotations

from aio.tools.brave_search import BraveSearchClient

_MAX_SNIPPET_CHARS = 220


def web_research_context(query: str, *, client: BraveSearchClient | None = None) -> str:
    client = client or BraveSearchClient()
    results = client.search(query)
    lines = [
        f"- {r['title']}: {r['snippet'][:_MAX_SNIPPET_CHARS]} ({r['url']})"
        for r in results
        if r.get("snippet")
    ]
    if not lines:
        return ""
    return (
        "\n\nLive web research (Brave Search -- ground your findings in "
        "this current information; prefer it over stale training-data "
        "assumptions where they conflict):\n" + "\n".join(lines)
    )
