from datetime import datetime, timezone

from aio.memory.long_term import LongTermMemory
from aio.memory.semantic import SemanticMemory
from aio.memory.short_term import ShortTermMemory
from aio.observability.execution_log import ExecutionMetrics


def test_short_term_memory_round_trip():
    memory = ShortTermMemory()
    memory.set("goal", "build a widget")
    assert memory.get("goal") == "build a widget"
    assert memory.get("missing", "default") == "default"
    assert memory.as_dict() == {"goal": "build a widget"}


def test_long_term_memory_persists_and_lists(tmp_path):
    db_url = f"sqlite:///{tmp_path}/test.db"
    memory = LongTermMemory(database_url=db_url)
    memory.init_schema()

    project = memory.save_project(
        goal="Launch a todo app",
        research_report_json='{"executive_summary": "todo apps are viable"}',
        research_review="APPROVE. Sound research.",
        research_approved=True,
        business_requirements_json='{"vision": {"statement": "..."}}',
        tech_plan="FastAPI + Postgres",
        review="APPROVE. Looks good.",
        approved=True,
    )

    fetched = memory.get_project(project.id)
    assert fetched is not None
    assert fetched.goal == "Launch a todo app"
    assert fetched.research_approved is True
    assert fetched.approved is True

    projects = memory.list_projects()
    assert len(projects) == 1
    assert projects[0].id == project.id


def test_long_term_memory_missing_project_returns_none(tmp_path):
    db_url = f"sqlite:///{tmp_path}/test.db"
    memory = LongTermMemory(database_url=db_url)
    memory.init_schema()

    assert memory.get_project("does-not-exist") is None


def test_long_term_memory_execution_log_round_trip(tmp_path):
    db_url = f"sqlite:///{tmp_path}/test.db"
    memory = LongTermMemory(database_url=db_url)
    memory.init_schema()

    started = datetime.now(timezone.utc)
    metrics = ExecutionMetrics(
        agent_role="Domain Expert",
        started_at=started,
        ended_at=started,
        duration_seconds=1.23,
        confidence=0.8,
        reasoning_summary="identified healthcare as the domain",
        handoff_target="Research Coordinator",
        error=None,
    )

    record = memory.save_execution_log(metrics, project_id="proj-1")
    assert record.id is not None

    logs = memory.list_execution_logs()
    assert len(logs) == 1
    assert logs[0].agent_role == "Domain Expert"
    assert logs[0].confidence == 0.8
    assert logs[0].project_id == "proj-1"


def test_semantic_memory_search_ranks_relevant_project_first():
    memory = SemanticMemory(location=":memory:", collection="test_projects")
    memory.init_collection()

    memory.upsert_project(
        project_id="11111111-1111-1111-1111-111111111111",
        goal="Build a todo list app with reminders",
        summary="APPROVE. Simple CRUD app with notification support.",
    )
    memory.upsert_project(
        project_id="22222222-2222-2222-2222-222222222222",
        goal="Build a payroll tax compliance engine",
        summary="APPROVE. Complex rules engine for tax jurisdictions.",
    )

    results = memory.search_similar("todo list reminders app", top_k=2)

    assert len(results) == 2
    assert results[0]["id"] == "11111111-1111-1111-1111-111111111111"
