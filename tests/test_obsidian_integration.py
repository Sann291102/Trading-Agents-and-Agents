import httpx

from aio.integrations.obsidian import ObsidianClient


def test_disabled_without_api_key_returns_false_no_network_call(monkeypatch):
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("httpx.put must not be called when no API key is configured")

    monkeypatch.setattr(httpx, "put", _fail_if_called)

    client = ObsidianClient(base_url="https://127.0.0.1:27124", api_key="")
    assert client.enabled is False
    assert client.write_note("JARVIS/test.md", "content") is False


def test_enabled_writes_note(monkeypatch):
    captured = {}

    def _fake_put(url, content=None, headers=None, timeout=None, verify=None):
        captured["url"] = url
        captured["content"] = content
        captured["headers"] = headers
        request = httpx.Request("PUT", url)
        return httpx.Response(200, request=request)

    monkeypatch.setattr(httpx, "put", _fake_put)

    client = ObsidianClient(base_url="https://127.0.0.1:27124", api_key="test-key")
    assert client.write_note("JARVIS/research_finding/abc.md", "# hello") is True
    assert captured["url"] == "https://127.0.0.1:27124/vault/JARVIS/research_finding/abc.md"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["content"] == b"# hello"


def test_request_failure_degrades_to_false(monkeypatch):
    def _raise(*args, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "put", _raise)

    client = ObsidianClient(base_url="https://127.0.0.1:27124", api_key="test-key")
    assert client.write_note("JARVIS/test.md", "content") is False
