"""Thin wrapper around the Anthropic Claude API.

This is the *only* LLM connector wired up in this vertical slice. Other
providers listed in the org-wide architecture (OpenAI, Google AI, Mistral,
etc.) are intentionally not implemented here -- swap or extend this class
when a second provider is needed, everything upstream depends on the
`AnthropicClient.complete` interface, not on the Anthropic SDK directly.
"""

from __future__ import annotations

from anthropic import Anthropic

from aio.config import settings


class AnthropicClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.model = model or settings.anthropic_model
        self._client = Anthropic(api_key=api_key or settings.anthropic_api_key)

    # 20000 is the ceiling before the Anthropic SDK starts requiring
    # streaming ("Streaming is required for operations that may take
    # longer than 10 minutes") -- confirmed empirically: 20000 is accepted
    # non-streaming, 24000 is not. Structured JSON responses for very
    # large goals can still exceed this and truncate (see
    # AgentOutputParseError); the real fix for that is switching this
    # method to streaming, not raising the constant further.
    def complete(self, system: str, user: str, max_tokens: int = 20000) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in response.content if block.type == "text"
        )
