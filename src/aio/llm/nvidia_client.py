"""OpenAI-compatible client for NVIDIA's hosted inference API (build.nvidia.com).

A second real LLM provider alongside `AnthropicClient` -- same
`complete(system, user, max_tokens)` interface, so `build_default_llm` can
swap it in via `LLM_PROVIDER=nvidia` with no changes anywhere else in the
codebase (every agent calls `self._llm.complete(...)`, never a
provider-specific method). Useful as a free-tier alternative to cut
Anthropic API spend during development; production deployments should still
choose a provider deliberately based on model quality/rate limits, not
default here.
"""

from __future__ import annotations

from openai import OpenAI

from aio.config import settings


class NvidiaClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.model = model or settings.nvidia_model
        self._client = OpenAI(
            base_url=settings.nvidia_base_url,
            api_key=api_key or settings.nvidia_api_key,
        )

    def _extra_body(self, max_tokens: int) -> dict:
        """Reasoning-control params differ per model family on NVIDIA's API.
        Nemotron accepts `reasoning_budget`; GLM (z-ai/glm-*) rejects it with
        a 400 and instead takes `clear_thinking` in its chat_template_kwargs.
        Sending the wrong one is a hard request failure, so pick by model."""
        model = self.model.lower()
        if model.startswith("z-ai/glm") or "glm" in model:
            return {"chat_template_kwargs": {"enable_thinking": True, "clear_thinking": False}}
        # Nemotron and other reasoning models that honor an explicit budget.
        return {
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_budget": max_tokens,
        }

    def complete(self, system: str, user: str, max_tokens: int = 20000) -> str:
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=1,
            top_p=0.95,
            max_tokens=max_tokens,
            extra_body=self._extra_body(max_tokens),
            stream=True,
        )
        # Nemotron's reasoning output arrives as two separate delta streams:
        # `reasoning_content` ("thinking") and `content` (the final answer).
        # Only the latter is returned -- callers parse this as the agent's
        # actual output (plain text or JSON per each agent's output_schema),
        # and thinking tokens mixed in would corrupt that parse.
        chunks: list[str] = []
        for chunk in stream:
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if content:
                chunks.append(content)
        return "".join(chunks)
