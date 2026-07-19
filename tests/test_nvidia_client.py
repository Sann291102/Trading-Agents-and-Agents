"""Unit tests for NvidiaClient's model-aware reasoning params.

No network: we only assert how the request body is built per model family.
GLM-5.2 rejects `reasoning_budget` with a 400 (verified live), so the client
must not send it for GLM models -- these tests lock that in.
"""

from __future__ import annotations

from aio.llm.nvidia_client import NvidiaClient


def _client(model: str) -> NvidiaClient:
    # api_key is required by the OpenAI ctor but never used (no call is made).
    return NvidiaClient(api_key="test-key", model=model)


def test_glm_omits_reasoning_budget():
    body = _client("z-ai/glm-5.2")._extra_body(4096)
    assert "reasoning_budget" not in body
    assert body["chat_template_kwargs"] == {"enable_thinking": True, "clear_thinking": False}


def test_glm_match_is_case_insensitive_and_substring():
    assert "reasoning_budget" not in _client("Z-AI/GLM-5.2")._extra_body(4096)
    assert "reasoning_budget" not in _client("some-vendor/glm-4-plus")._extra_body(4096)


def test_nemotron_keeps_reasoning_budget():
    body = _client("nvidia/nemotron-3-ultra-550b-a55b")._extra_body(4096)
    assert body["reasoning_budget"] == 4096
    assert body["chat_template_kwargs"] == {"enable_thinking": True}
