"""API gateway for the AI Organization vertical slice.

A single FastAPI service standing in for the full platform's API gateway +
auth/RBAC layer (not implemented in this slice -- see ARCHITECTURE.md for
the roadmap). It exposes the one workflow this slice supports: hand the
organization a goal, get back what Research, Product, and Engineering
produced -- research is now a mandatory stage before Product acts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from aio.agents.registry import agent_status_tracker, all_agent_classes
from aio.config import settings
from aio.events.bus import event_bus
from aio.memory.long_term import LongTermMemory
from aio.memory.semantic import SemanticMemory
from aio.memory.service import MemoryService
from aio.observability.logging_setup import setup_logging
from aio.orchestration import cancellation
from aio.orchestration.cancellation import MissionCancelled
from aio.orchestration.graph import run_organization
from aio.preview import preview_manager
from aio.preview.manager import _resolve as _resolve_preview_path

# At import time, not in lifespan: uvicorn imports this module before
# serving, and agent/module loggers must be capturing from the first line.
setup_logging()

logger = logging.getLogger("aio.api.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    long_term = LongTermMemory()
    long_term.init_schema()
    semantic = SemanticMemory()
    semantic.init_collection()
    memory = MemoryService()
    memory.init_schema()
    app.state.long_term = long_term
    app.state.semantic = semantic
    app.state.memory = memory
    # Every OrgEvent published anywhere in the process (agents, graph
    # nodes, memory writes) must reach SSE subscribers on *this* loop --
    # see events/bus.py's module docstring for why this bind is required.
    event_bus.bind_loop(asyncio.get_running_loop())
    yield
    # Never let a `next dev` preview child outlive this process (uvicorn
    # --reload restarts, Ctrl-C, container stop).
    preview_manager.stop_all()


app = FastAPI(title="AI Organization (vertical slice)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GoalRequest(BaseModel):
    goal: str


class StartProjectResponse(BaseModel):
    project_id: str


class ProjectResponse(BaseModel):
    id: str
    goal: str
    research_report: dict | None = None
    research_review: str = ""
    research_approved: bool = False
    business_requirements: dict | None = None
    tech_plan: str = ""
    review: str = ""
    approved: bool = False
    # Engineering-swarm stage.
    swarm_plan: dict | None = None
    swarm_results: list[dict] | None = None
    swarm_validation: dict | None = None
    # Live-preview stage.
    preview_url: str | None = None
    preview_error: str | None = None


def _parse_json_field(raw: str) -> dict | None:
    return json.loads(raw) if raw else None


def _parse_json_list_field(raw: str) -> list[dict] | None:
    return json.loads(raw) if raw else None


def _resolve_preview_dir(project_id: str):
    # Same resolution PreviewManager.start() uses (settings.preview_workspace_dir
    # / project_id, anchored at the repo root, not the process cwd) -- reused
    # directly rather than duplicated, so this can never drift from where
    # files are actually written.
    return _resolve_preview_path(settings.preview_workspace_dir) / project_id


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "model": settings.anthropic_model if settings.llm_provider == "anthropic" else "demo",
    }


@app.get("/agents")
def list_agents() -> list[dict]:
    """Every implemented agent plus its live status, derived only from real
    agent_started/agent_finished events (see agents/registry.py). Adding a
    new department/agent requires no change here -- it appears the moment
    its `Agent` subclass is imported anywhere in the process."""
    statuses = {status.role: status for status in agent_status_tracker.snapshot()}
    agents = []
    for cls in all_agent_classes():
        status = statuses.get(cls.role)
        agents.append(
            {
                "role": cls.role,
                "department": cls.department,
                "status": status.status if status else "idle",
                "last_confidence": status.last_confidence if status else None,
                "last_duration_seconds": status.last_duration_seconds if status else None,
                "last_project_id": status.last_project_id if status else None,
                "last_message": status.last_message if status else "",
            }
        )
    return agents


@app.get("/events/stream", response_class=EventSourceResponse)
async def stream_events():
    """Live organization event feed -- agent lifecycle, handoffs, reviews,
    memory writes. Every event corresponds to something that actually
    happened in `run_organization`/`Agent.run_logged`/memory writes; there
    is no synthetic/timer-driven activity on this stream.

    Replays the last 20 events on connect (so a client that connects mid-run
    isn't blind to what already happened), then streams live.
    """
    queue = event_bus.subscribe()
    try:
        for event in event_bus.recent(20):
            yield ServerSentEvent(event=event.type, id=event.id, data=event.model_dump())
        while True:
            event = await queue.get()
            yield ServerSentEvent(event=event.type, id=event.id, data=event.model_dump())
    finally:
        event_bus.unsubscribe(queue)


def _run_mission_in_background(goal: str, project_id: str) -> None:
    try:
        run_organization(
            goal,
            long_term=app.state.long_term,
            semantic=app.state.semantic,
            memory=app.state.memory,
            project_id=project_id,
        )
    except MissionCancelled:
        pass  # run_organization already published workflow_cancelled
    except Exception:
        # run_organization already published workflow_failed on the event
        # bus (the frontend's real signal) -- this is only so the failure
        # also reaches the server's own logs, since nothing awaits this
        # thread to see the exception otherwise.
        logger.exception("mission %s failed", project_id)


@app.post("/projects", response_model=StartProjectResponse, status_code=202)
def create_project(request: GoalRequest) -> StartProjectResponse:
    """Kicks off the mission on a background thread and returns its
    project_id immediately -- a real run is a dozen-plus sequential/parallel
    LLM calls, too long to hold the HTTP connection open for, and the
    frontend already gets live progress from the SSE stream independent of
    this response. Registering the cancellation event here (not just inside
    `run_organization`) means a `POST /projects/{id}/cancel` can never race
    ahead of the mission actually starting -- see cancellation.register's
    docstring."""
    project_id = str(uuid.uuid4())
    cancellation.register(project_id)
    threading.Thread(
        target=_run_mission_in_background,
        args=(request.goal, project_id),
        daemon=True,
    ).start()
    return StartProjectResponse(project_id=project_id)


@app.post("/projects/{project_id}/cancel")
def cancel_project(project_id: str) -> dict:
    if not cancellation.request_cancel(project_id):
        raise HTTPException(status_code=404, detail="no running mission with that id")
    return {"status": "cancel_requested"}


@app.get("/projects")
def list_projects(limit: int = 50) -> list[dict]:
    """Lightweight project list for the Knowledge Universe view -- full
    research/BRD payloads are fetched per-project via GET /projects/{id}
    once a node is selected, not eagerly for every project in the list."""
    projects = app.state.long_term.list_projects(limit=limit)
    return [
        {
            "id": p.id,
            "goal": p.goal,
            "approved": p.approved,
            "research_approved": p.research_approved,
            "created_at": p.created_at.isoformat(),
        }
        for p in projects
    ]


@app.get("/projects/search")
def search_projects(q: str, top_k: int = 5) -> list[dict]:
    return app.state.semantic.search_similar(q, top_k=top_k)


@app.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str) -> ProjectResponse:
    project = app.state.long_term.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return ProjectResponse(
        id=project.id,
        goal=project.goal,
        research_report=_parse_json_field(project.research_report_json),
        research_review=project.research_review,
        research_approved=project.research_approved,
        business_requirements=_parse_json_field(project.business_requirements_json),
        tech_plan=project.tech_plan,
        review=project.review,
        approved=project.approved,
        swarm_plan=_parse_json_field(project.swarm_plan_json),
        swarm_results=_parse_json_list_field(project.swarm_results_json),
        swarm_validation=_parse_json_field(project.swarm_validation_json),
        preview_url=project.preview_url or None,
        preview_error=project.preview_error or None,
    )


@app.get("/projects/{project_id}/files")
def list_project_files(project_id: str) -> list[str]:
    """Where a mission's generated code actually lands on disk -- there's no
    DB manifest table (the files themselves are the record, and they persist
    on disk after the preview server stops -- see preview/manager.py), so
    this walks `workspace/previews/<project_id>` fresh on every request."""
    project_dir = _resolve_preview_dir(project_id)
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail="no generated files for this project")
    return sorted(
        str(path.relative_to(project_dir)).replace("\\", "/")
        for path in project_dir.rglob("*")
        if path.is_file()
    )


@app.get("/memory-entries")
def list_memory_entries(limit: int = 50) -> list[dict]:
    """Durable organizational memory: research findings, risks, and (later)
    architectural decisions recorded per run -- see memory/recording.py and
    ARCHITECTURE.md roadmap item #4. List-only, matching MemoryService's
    deliberately CRUD-only surface (no filtering/relevance ranking yet)."""
    entries = app.state.memory.list_entries(limit=limit)
    return [entry.model_dump(mode="json") for entry in entries]


@app.get("/execution-logs")
def list_execution_logs(limit: int = 100) -> list[dict]:
    logs = app.state.long_term.list_execution_logs(limit=limit)
    return [
        {
            "id": log.id,
            "project_id": log.project_id,
            "agent_role": log.agent_role,
            "started_at": log.started_at.isoformat(),
            "ended_at": log.ended_at.isoformat(),
            "duration_seconds": log.duration_seconds,
            "confidence": log.confidence,
            "reasoning_summary": log.reasoning_summary,
            "handoff_target": log.handoff_target,
            "error": log.error,
        }
        for log in logs
    ]
