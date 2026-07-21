"""Generic client for any OpenAI-compatible chat-completions endpoint.

Connects JARVIS to LLM routers like OmniRoute or OpenRouter (free-token
tiers), or a local vLLM/Ollama server -- anything that speaks the standard
OpenAI chat API. Same `complete(system, user, max_tokens)` interface as
every other provider, selected via `LLM_PROVIDER=openai_compat`. Unlike
`NvidiaClient`, no vendor-specific reasoning params are sent, so a
standards-compliant router never 400s on unknown fields.
"""

from __future__ import annotations

from openai import OpenAI

from aio.config import settings


class OpenAICompatClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model or settings.openai_compat_model
        resolved_base_url = base_url or settings.openai_compat_base_url
        if not resolved_base_url:
            raise ValueError(
                "LLM_PROVIDER=openai_compat requires OPENAI_COMPAT_BASE_URL in .env "
                "(e.g. your OmniRoute endpoint)"
            )
        if not self.model:
            raise ValueError("LLM_PROVIDER=openai_compat requires OPENAI_COMPAT_MODEL in .env")
        self._client = OpenAI(
            base_url=resolved_base_url,
            api_key=api_key or settings.openai_compat_api_key or "unused",
        )

    def complete(self, system: str, user: str, max_tokens: int = 20000) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
