from .anthropic_client import AnthropicClient
from .demo_client import DemoAnthropicClient
from .nvidia_client import NvidiaClient
from .openai_compat_client import OpenAICompatClient
from .resilient import ResilientLLMClient


def _build_raw_llm():
    """Reads `settings.llm_provider` fresh every call -- so a provider
    switch (edit `.env`, then `POST /admin/reload-config` or wait for the
    next auto-retry, see `ResilientLLMClient`) takes effect without a
    process restart."""
    from aio.config import settings

    if settings.llm_provider == "demo":
        return DemoAnthropicClient()
    if settings.llm_provider == "nvidia":
        return NvidiaClient()
    if settings.llm_provider == "openai_compat":
        return OpenAICompatClient()
    return AnthropicClient()


def build_default_llm():
    """The LLM client `run_organization` uses when the caller doesn't pass
    one explicitly. Wrapped in `ResilientLLMClient` so a mission survives
    the operator changing the provider/key mid-run: a failed call reloads
    settings and retries once against a freshly built client instead of
    dying on stale config. See resilient.py."""
    return ResilientLLMClient(_build_raw_llm)


__all__ = [
    "AnthropicClient",
    "DemoAnthropicClient",
    "NvidiaClient",
    "OpenAICompatClient",
    "ResilientLLMClient",
    "build_default_llm",
]
