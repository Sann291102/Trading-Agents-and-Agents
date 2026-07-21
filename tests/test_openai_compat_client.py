"""OpenAICompatClient -- the generic OpenAI-compatible provider path
(OmniRoute/OpenRouter/local vLLM) selected via LLM_PROVIDER=openai_compat."""

import pytest

from aio.config import settings
from aio.llm import OpenAICompatClient
from aio.llm import _build_raw_llm


@pytest.fixture()
def _compat_settings(monkeypatch):
    monkeypatch.setattr(settings, "openai_compat_base_url", "https://router.example/v1")
    monkeypatch.setattr(settings, "openai_compat_model", "some/free-model")
    monkeypatch.setattr(settings, "openai_compat_api_key", "sk-test")


def test_build_raw_llm_selects_openai_compat(monkeypatch, _compat_settings):
    monkeypatch.setattr(settings, "llm_provider", "openai_compat")
    client = _build_raw_llm()
    assert isinstance(client, OpenAICompatClient)
    assert client.model == "some/free-model"


def test_missing_base_url_is_a_clear_config_error(monkeypatch):
    monkeypatch.setattr(settings, "openai_compat_base_url", "")
    monkeypatch.setattr(settings, "openai_compat_model", "some/free-model")
    with pytest.raises(ValueError, match="OPENAI_COMPAT_BASE_URL"):
        OpenAICompatClient()


def test_missing_model_is_a_clear_config_error(monkeypatch):
    monkeypatch.setattr(settings, "openai_compat_base_url", "https://router.example/v1")
    monkeypatch.setattr(settings, "openai_compat_model", "")
    with pytest.raises(ValueError, match="OPENAI_COMPAT_MODEL"):
        OpenAICompatClient()
