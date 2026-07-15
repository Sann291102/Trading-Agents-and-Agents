import time

from fastapi.testclient import TestClient

from aio.agents.registry import all_agent_classes
from aio.api.main import app
from aio.config import settings
from aio.memory.long_term import LongTermMemory
from aio.memory.semantic import SemanticMemory
from aio.memory.service import MemoryService

VALID_STATUSES = {"idle", "executing", "completed", "needs_review"}


def test_projects_search_route_is_registered_before_project_id_route():
    """Regression test: /projects/search must resolve to search_projects, not
    get_project("search"). FastAPI/Starlette match routes in registration
    order, so a literal path registered after a same-prefix path parameter
    route gets silently shadowed by it."""
    paths_with_get = [
        route.path
        for route in app.routes
        if hasattr(route, "methods") and "GET" in route.methods
        and route.path.startswith("/projects")
    ]

    assert paths_with_get.index("/projects/search") < paths_with_get.index(
        "/projects/{project_id}"
    )


def _client() -> TestClient:
    # Deliberately not `with TestClient(app) as client:` -- that would run
    # the real lifespan, which points app.state.long_term/semantic at
    # Postgres/Qdrant via default settings. Endpoints that need app.state
    # (projects/execution-logs) get it wired manually below instead.
    return TestClient(app)


def test_health_endpoint():
    response = _client().get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == settings.llm_provider
    assert body["model"]


def test_agents_endpoint_lists_every_implemented_agent_with_valid_status():
    """Doesn't assert a specific status value -- agent_status_tracker is a
    process-wide singleton, so whatever other tests ran earlier in this
    session may have already moved some roles out of 'idle'. What must
    hold regardless of test order: every implemented role/department
    appears, and status is always one of the real, documented values."""
    response = _client().get("/agents")
    assert response.status_code == 200

    body = response.json()
    roles = {entry["role"] for entry in body}
    expected_roles = {cls.role for cls in all_agent_classes()}
    assert roles == expected_roles

    for entry in body:
        assert entry["status"] in VALID_STATUSES
        assert entry["department"]


def test_projects_and_execution_logs_endpoints_use_wired_memory(tmp_path):
    db_url = f"sqlite:///{tmp_path}/test.db"
    long_term = LongTermMemory(database_url=db_url)
    long_term.init_schema()
    semantic = SemanticMemory(location=":memory:", collection="test_api_projects")
    semantic.init_collection()

    project = long_term.save_project(
        goal="Launch a widget",
        research_report_json="",
        research_review="",
        research_approved=False,
        business_requirements_json="",
        tech_plan="",
        review="APPROVE",
        approved=True,
    )

    app.state.long_term = long_term
    app.state.semantic = semantic
    try:
        client = _client()

        projects = client.get("/projects").json()
        assert any(p["id"] == project.id and p["goal"] == "Launch a widget" for p in projects)

        detail = client.get(f"/projects/{project.id}")
        assert detail.status_code == 200
        assert detail.json()["approved"] is True

        missing = client.get("/projects/does-not-exist")
        assert missing.status_code == 404

        logs = client.get("/execution-logs")
        assert logs.status_code == 200
        assert isinstance(logs.json(), list)
    finally:
        del app.state.long_term
        del app.state.semantic


def test_create_project_end_to_end_via_http_with_demo_llm(tmp_path):
    """The one test that exercises the full HTTP path (POST /projects kicks
    off run_organization on a background thread and returns immediately ->
    poll GET /projects/{id} for the persisted result), using the same demo
    LLM provider documented for cost-free verification. The underlying
    pipeline is already covered thoroughly by test_demo_client.py; this just
    proves the API layer wires the async kickoff up and shapes the
    eventually-persisted response correctly."""
    db_url = f"sqlite:///{tmp_path}/test.db"
    long_term = LongTermMemory(database_url=db_url)
    long_term.init_schema()
    semantic = SemanticMemory(location=":memory:", collection="test_api_create_project")
    semantic.init_collection()
    memory = MemoryService(database_url=db_url)
    memory.init_schema()

    app.state.long_term = long_term
    app.state.semantic = semantic
    app.state.memory = memory
    original_provider = settings.llm_provider
    settings.llm_provider = "demo"
    try:
        client = _client()
        start = client.post("/projects", json={"goal": "Launch a customer feedback widget"})
        assert start.status_code == 202
        project_id = start.json()["project_id"]

        # The mission runs on a background thread; the demo LLM has no real
        # network I/O so this finishes almost instantly, but it's still a
        # genuine race -- poll with a short timeout rather than assuming it's
        # done by the time this line runs.
        body = None
        for _ in range(50):
            detail = client.get(f"/projects/{project_id}")
            if detail.status_code == 200:
                body = detail.json()
                break
            time.sleep(0.1)
        assert body is not None, "mission did not persist within the poll timeout"

        assert body["approved"] is True
        assert body["business_requirements"]["epics"]
        assert body["research_report"]["executive_summary"]
        assert body["swarm_plan"]["assignments"]
        assert body["swarm_results"]
        assert body["swarm_validation"]["passed"] is True

        # The run should have recorded durable organizational memory, and
        # GET /memory-entries should surface it (list-only endpoint).
        entries = client.get("/memory-entries").json()
        assert any(e["type"] == "research_finding" for e in entries)
        assert all(0.0 <= e["confidence"] <= 1.0 for e in entries)
    finally:
        settings.llm_provider = original_provider
        del app.state.long_term
        del app.state.semantic
        del app.state.memory
