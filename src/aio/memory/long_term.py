"""Durable, structured memory: one row per completed orchestration run.

Backed by Postgres. This is the organization's system of record -- what was
asked, what Research found, what Product/Engineering produced, and whether
the CEO approved each stage. Also stores per-agent execution logs for
observability/analytics (see observability/execution_log.py).
"""

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from aio.config import settings
from aio.db.models import Base, ExecutionLogRecord, Project
from aio.events.bus import OrgEvent, event_bus
from aio.observability.execution_log import ExecutionMetrics


class LongTermMemory:
    def __init__(self, database_url: str | None = None) -> None:
        self._engine = create_engine(database_url or settings.database_url, future=True)
        self._Session: sessionmaker[Session] = sessionmaker(bind=self._engine, future=True)

    def init_schema(self) -> None:
        Base.metadata.create_all(self._engine)

    def save_project(
        self,
        goal: str,
        research_report_json: str,
        research_review: str,
        research_approved: bool,
        business_requirements_json: str,
        tech_plan: str,
        review: str,
        approved: bool,
        id: str | None = None,
        swarm_plan_json: str = "",
        swarm_results_json: str = "",
        swarm_validation_json: str = "",
        preview_url: str = "",
        preview_error: str = "",
    ) -> Project:
        with self._Session() as session:
            kwargs = dict(
                goal=goal,
                research_report_json=research_report_json,
                research_review=research_review,
                research_approved=research_approved,
                business_requirements_json=business_requirements_json,
                tech_plan=tech_plan,
                review=review,
                approved=approved,
                swarm_plan_json=swarm_plan_json,
                swarm_results_json=swarm_results_json,
                swarm_validation_json=swarm_validation_json,
                preview_url=preview_url,
                preview_error=preview_error,
            )
            if id is not None:
                kwargs["id"] = id
            project = Project(**kwargs)
            session.add(project)
            session.commit()
            session.refresh(project)

        event_bus.publish(
            OrgEvent(
                type="memory_updated",
                department="Executive",
                project_id=project.id,
                message=f"Project record saved (approved={approved})",
            )
        )
        return project

    def get_project(self, project_id: str) -> Project | None:
        with self._Session() as session:
            return session.get(Project, project_id)

    def list_projects(self, limit: int = 50) -> list[Project]:
        with self._Session() as session:
            stmt = select(Project).order_by(Project.created_at.desc()).limit(limit)
            return list(session.scalars(stmt))

    def save_execution_log(
        self, metrics: ExecutionMetrics, project_id: str | None = None
    ) -> ExecutionLogRecord:
        with self._Session() as session:
            record = ExecutionLogRecord(
                project_id=project_id,
                agent_role=metrics.agent_role,
                started_at=metrics.started_at,
                ended_at=metrics.ended_at,
                duration_seconds=metrics.duration_seconds,
                confidence=metrics.confidence,
                reasoning_summary=metrics.reasoning_summary,
                handoff_target=metrics.handoff_target,
                error=metrics.error,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_execution_logs(self, limit: int = 100) -> list[ExecutionLogRecord]:
        with self._Session() as session:
            stmt = (
                select(ExecutionLogRecord)
                .order_by(ExecutionLogRecord.created_at.desc())
                .limit(limit)
            )
            return list(session.scalars(stmt))
