import pytest

from aio.config import settings
from aio.connectors import (
    Capability,
    Connector,
    all_connectors,
    connector_available,
    get_connector,
    register_connector,
)


def test_unknown_connector_is_unavailable_and_does_not_raise():
    # The action registry calls this while building the planner's menu, so a
    # stale or misspelled name must cost one action, not the whole cycle.
    assert connector_available("definitely-not-a-connector") is False
    assert get_connector("definitely-not-a-connector") is None


def test_builtins_are_registered():
    assert {connector.name for connector in all_connectors()} >= {
        "obsidian",
        "n8n",
        "brave",
        "memory",
    }


def test_memory_connector_is_always_available():
    memory = get_connector("memory")
    assert memory is not None
    assert memory.available() is True
    assert connector_available("memory") is True

    status = memory.status()
    assert status["available"] is True
    assert status["setup_hint"] == ""
    assert Capability.WRITE.value in status["capabilities"]


@pytest.mark.parametrize(
    ("name", "config_field", "env_var"),
    [
        ("obsidian", "obsidian_api_key", "OBSIDIAN_API_KEY"),
        ("n8n", "n8n_base_url", "N8N_BASE_URL"),
        ("brave", "brave_api_key", "BRAVE_API_KEY"),
    ],
)
def test_unconfigured_external_connector_reports_unavailable_with_setup_hint(
    monkeypatch, name, config_field, env_var
):
    monkeypatch.setattr(settings, config_field, "")

    assert connector_available(name) is False

    status = get_connector(name).status()
    assert status["available"] is False
    assert env_var in status["setup_hint"]
    assert status["name"] == name


@pytest.mark.parametrize(
    ("name", "config_field", "value"),
    [
        ("obsidian", "obsidian_api_key", "test-key"),
        ("n8n", "n8n_base_url", "http://localhost:5678"),
        ("brave", "brave_api_key", "test-key"),
    ],
)
def test_configured_external_connector_becomes_available(monkeypatch, name, config_field, value):
    # Availability is read live so `settings.reload()` switches a connector on
    # without a process restart.
    monkeypatch.setattr(settings, config_field, value)

    assert connector_available(name) is True
    status = get_connector(name).status()
    assert status["available"] is True
    assert status["setup_hint"] == ""


def test_status_shape_is_uniform_across_connectors():
    for connector in all_connectors():
        status = connector.status()
        assert set(status) == {
            "name",
            "display_name",
            "description",
            "capabilities",
            "available",
            "setup_hint",
        }
        assert status["display_name"] and status["description"]
        assert status["capabilities"]
        assert isinstance(status["available"], bool)


def test_broken_availability_check_degrades_instead_of_raising():
    class ExplodingConnector(Connector):
        name = "exploding-test-connector"
        display_name = "Exploding"
        description = "Raises on every config check."
        capabilities = (Capability.OBSERVE,)
        setup_hint = "Nothing will help."

        def available(self) -> bool:
            raise RuntimeError("config lookup blew up")

    register_connector(ExplodingConnector())
    try:
        assert connector_available("exploding-test-connector") is False
        assert get_connector("exploding-test-connector").status()["available"] is False
    finally:
        from aio.connectors import base

        base._REGISTRY.pop("exploding-test-connector", None)


def test_action_registry_filters_on_connector_availability(monkeypatch):
    # The contract the whole platform exists for: an action whose connector is
    # unconfigured still exists, but is never offered to the planner.
    from pydantic import BaseModel

    from aio.actions.base import ActionOutcome, ActionResult, ActionRisk
    from aio.actions.registry import _REGISTRY, all_actions, available_actions, action

    class _Params(BaseModel):
        query: str = ""

    @action(
        name="connector_test_search",
        description="Search the web (test action)",
        risk=ActionRisk.SAFE,
        params_model=_Params,
        connector="brave",
    )
    def _handler(context, params):  # pragma: no cover - never executed here
        return ActionResult(outcome=ActionOutcome.EXECUTED, summary="searched")

    try:
        monkeypatch.setattr(settings, "brave_api_key", "")
        names = {spec.name for spec in available_actions()}
        assert "connector_test_search" not in names
        assert "connector_test_search" in {spec.name for spec in all_actions()}

        monkeypatch.setattr(settings, "brave_api_key", "test-key")
        assert "connector_test_search" in {spec.name for spec in available_actions()}
    finally:
        _REGISTRY.pop("connector_test_search", None)
