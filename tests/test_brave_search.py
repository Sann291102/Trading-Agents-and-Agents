import httpx
import pytest

from aio.tools.brave_search import BraveSearchClient


def test_disabled_without_api_key_returns_empty_list_no_network_call(monkeypatch):
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("httpx.get must not be called when no API key is configured")

    monkeypatch.setattr(httpx, "get", _fail_if_called)

    client = BraveSearchClient(api_key="")
    assert client.enabled is False
    assert client.search("anything") == []


def test_enabled_parses_results(monkeypatch):
    def _fake_get(url, params=None, headers=None, timeout=None):
        assert headers["X-Subscription-Token"] == "test-key"
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "web": {
                    "results": [
                        {"title": "A", "description": "snippet A", "url": "https://a.example"},
                        {"title": "B", "description": "snippet B", "url": "https://b.example"},
                    ]
                }
            },
        )

    monkeypatch.setattr(httpx, "get", _fake_get)

    client = BraveSearchClient(api_key="test-key")
    assert client.enabled is True
    results = client.search("query", count=5)
    assert results == [
        {"title": "A", "url": "https://a.example", "snippet": "snippet A"},
        {"title": "B", "url": "https://b.example", "snippet": "snippet B"},
    ]


def test_request_failure_degrades_to_empty_list(monkeypatch):
    def _raise(*args, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "get", _raise)

    client = BraveSearchClient(api_key="test-key")
    assert client.search("query") == []
