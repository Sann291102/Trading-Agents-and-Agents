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
from aio.orchestration.graph import run_organization
from aio.preview import preview_manager

# At import time, not in lifespan: uvicorn imports this module before
# serving, and agent/module loggers must be capturing from the first line.
setup_logging()


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
    # Engineering-swarm stage (not yet persisted -- populated on the
    # POST /projects response for the run that just happened).
    swarm_plan: dict | None = None
    swarm_results: list[dict] | None = None
    swarm_validation: dict | None = None
    # Live-preview stage (also not yet persisted -- see swarm fields above).
    preview_url: str | None = None
    preview_error: str | None = None


def _parse_json_field(raw: str) -> dict | None:
    return json.loads(raw) if raw else None


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


@app.post("/projects", response_model=ProjectResponse)
def create_project(request: GoalRequest) -> ProjectResponse:
    result = run_organization(
        request.goal,
        long_term=app.state.long_term,
        semantic=app.state.semantic,
        memory=app.state.memory,
    )
    research_report = result.get("research_report")
    business_requirements = result.get("business_requirements")
    return ProjectResponse(
        id=result["project_id"],
        goal=request.goal,
        research_report=research_report.model_dump() if research_report else None,
        research_review=result.get("research_review", ""),
        research_approved=result.get("research_approved", False),
        business_requirements=(
            business_requirements.model_dump() if business_requirements else None
        ),
        tech_plan=result.get("tech_plan", ""),
        review=result.get("review", ""),
        approved=result.get("approved", False),
        swarm_plan=(
            result["swarm_plan"].model_dump() if result.get("swarm_plan") else None
        ),
        swarm_results=(
            [r.model_dump() for r in result["swarm_results"]]
            if result.get("swarm_results")
            else None
        ),
        swarm_validation=(
            result["swarm_validation"].model_dump() if result.get("swarm_validation") else None
        ),
        preview_url=result.get("preview_url"),
        preview_error=result.get("preview_error"),
    )


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
