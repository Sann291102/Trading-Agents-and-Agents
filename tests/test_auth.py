"""Signup/login and endpoint gating -- see aio/auth/service.py and
api/main.py's get_current_user dependency. Unlike test_api.py, this file
does NOT bypass auth (no dependency_overrides): it's specifically testing
that the gate is real.
"""

import uuid

from fastapi.testclient import TestClient

from aio.api.main import app
from aio.auth import AuthService


def _client() -> TestClient:
    return TestClient(app)


def _fresh_auth(tmp_path) -> AuthService:
    auth = AuthService(database_url=f"sqlite:///{tmp_path}/auth.db")
    auth.init_schema()
    app.state.auth = auth
    return auth


def test_signup_then_login_round_trip(tmp_path):
    _fresh_auth(tmp_path)
    client = _client()
    username = f"user-{uuid.uuid4().hex[:8]}"

    signup = client.post("/auth/signup", json={"username": username, "password": "correcthorse"})
    assert signup.status_code == 201
    assert signup.json()["token"]

    login = client.post("/auth/login", json={"username": username, "password": "correcthorse"})
    assert login.status_code == 200
    assert login.json()["token"]
    # Each successful auth issues its own session -- tokens need not match.
    assert login.json()["token"] != signup.json()["token"]


def test_signup_rejects_duplicate_username(tmp_path):
    _fresh_auth(tmp_path)
    client = _client()
    username = f"user-{uuid.uuid4().hex[:8]}"

    first = client.post("/auth/signup", json={"username": username, "password": "correcthorse"})
    assert first.status_code == 201

    second = client.post("/auth/signup", json={"username": username, "password": "differentpw"})
    assert second.status_code == 409


def test_signup_rejects_short_password(tmp_path):
    _fresh_auth(tmp_path)
    client = _client()
    response = client.post(
        "/auth/signup", json={"username": f"user-{uuid.uuid4().hex[:8]}", "password": "short"}
    )
    assert response.status_code == 400


def test_login_rejects_wrong_password(tmp_path):
    _fresh_auth(tmp_path)
    client = _client()
    username = f"user-{uuid.uuid4().hex[:8]}"
    client.post("/auth/signup", json={"username": username, "password": "correcthorse"})

    response = client.post("/auth/login", json={"username": username, "password": "wrongpass"})
    assert response.status_code == 401


def test_login_rejects_unknown_username(tmp_path):
    _fresh_auth(tmp_path)
    response = _client().post(
        "/auth/login", json={"username": "no-such-user", "password": "whatever1"}
    )
    assert response.status_code == 401


def test_protected_endpoint_rejects_missing_token(tmp_path):
    _fresh_auth(tmp_path)
    response = _client().get("/agents")
    assert response.status_code == 401


def test_protected_endpoint_rejects_garbage_token(tmp_path):
    _fresh_auth(tmp_path)
    response = _client().get("/agents", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_protected_endpoint_accepts_a_real_session_token(tmp_path):
    _fresh_auth(tmp_path)
    client = _client()
    username = f"user-{uuid.uuid4().hex[:8]}"
    signup = client.post("/auth/signup", json={"username": username, "password": "correcthorse"})
    token = signup.json()["token"]

    response = client.get("/agents", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_health_endpoint_does_not_require_auth(tmp_path):
    _fresh_auth(tmp_path)
    assert _client().get("/health").status_code == 200
