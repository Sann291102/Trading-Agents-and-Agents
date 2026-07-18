import httpx

from aio.integrations.n8n import N8nClient


def test_disabled_without_base_url_returns_false_no_network_call(monkeypatch):
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("httpx.post must not be called when no base URL is configured")

    monkeypatch.setattr(httpx, "post", _fail_if_called)

    client = N8nClient(base_url="", api_key="")
    assert client.enabled is False
    assert client.notify_mission_complete({"project_id": "abc"}) is False


def test_enabled_posts_payload(monkeypatch):
    captured = {}

    def _fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request)

    monkeypatch.setattr(httpx, "post", _fake_post)

    client = N8nClient(base_url="http://localhost:5678", api_key="test-key")
    assert client.notify_mission_complete({"project_id": "abc"}) is True
    assert captured["url"] == "http://localhost:5678/webhook/jarvis-mission-complete"
    assert captured["json"] == {"project_id": "abc"}
    assert captured["headers"]["Authorization"] == "Bearer test-key"


def test_request_failure_degrades_to_false(monkeypatch):
    def _raise(*args, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "post", _raise)

    client = N8nClient(base_url="http://localhost:5678", api_key="")
    assert client.notify_mission_complete({}) is False
