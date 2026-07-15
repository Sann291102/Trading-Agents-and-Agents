from .anthropic_client import AnthropicClient
from .demo_client import DemoAnthropicClient
from .nvidia_client import NvidiaClient


def build_default_llm():
    """The LLM client `run_organization` uses when the caller doesn't pass
    one explicitly -- reads `settings.llm_provider` so a demo run can be
    triggered over the real API without a paid Anthropic key, or a real run
    can go through NVIDIA's hosted API instead of Anthropic. See
    demo_client.py's and nvidia_client.py's module docstrings."""
    from aio.config import settings

    if settings.llm_provider == "demo":
        return DemoAnthropicClient()
    if settings.llm_provider == "nvidia":
        return NvidiaClient()
    return AnthropicClient()


__all__ = ["AnthropicClient", "DemoAnthropicClient", "NvidiaClient", "build_default_llm"]
