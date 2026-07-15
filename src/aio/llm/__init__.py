from .anthropic_client import AnthropicClient
from .demo_client import DemoAnthropicClient


def build_default_llm():
    """The LLM client `run_organization` uses when the caller doesn't pass
    one explicitly -- reads `settings.llm_provider` so a demo run can be
    triggered over the real API without a paid Anthropic key. See
    demo_client.py's module docstring."""
    from aio.config import settings

    if settings.llm_provider == "demo":
        return DemoAnthropicClient()
    return AnthropicClient()


__all__ = ["AnthropicClient", "DemoAnthropicClient", "build_default_llm"]
