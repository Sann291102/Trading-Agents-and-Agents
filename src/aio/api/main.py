"""API gateway for the AI Organization vertical slice.

A single FastAPI service standing in for the full platform's API gateway.
Basic username/password auth now gates most of it (see auth/service.py) --
full RBAC/multi-department authorization is still a roadmap item (see
ARCHITECTURE.md), but every operator-facing endpoint below requires a valid
session. It exposes the one workflow this slice supports: hand the
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

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from aio.agents.registry import agent_status_tracker, all_agent_classes
from aio.agents.business import ChiefOfStaffAgent, ExecutiveAssistantAgent
from aio.auth import AuthService, InvalidCredentials, UsernameTaken
from aio.business import BusinessService
from aio.models.business import (
    Approval,
    BusinessMetricSnapshot,
    Company,
    ConversationTurn,
    Milestone,
    next_stage,
)
from aio.config import settings
from aio.db.models import User
from aio.events.bus import event_bus
from aio.llm import build_default_llm
from aio.memory.long_term import LongTermMemory
from aio.memory.semantic import SemanticMemory
from aio.memory.service import MemoryService
from aio.observability.logging_setup import setup_logging
from aio.orchestration import cancellation
from aio.orchestration.cancellation import MissionCancelled
from aio.orchestration.graph import resumable_goal, LangGraphOrchestrator
from aio.preview import preview_manager
from aio.preview.manager import _resolve as _resolve_preview_path
from aio.os.digital_twin import get_digital_twin
from aio.os.kernel import get_kernel

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
    auth = AuthService()
    auth.init_schema()
    business = BusinessService()
    business.init_schema()
    app.state.business = business
    app.state.long_term = long_term
    app.state.semantic = semantic
    app.state.memory = memory
    app.state.auth = auth
    app.state.orchestrator = LangGraphOrchestrator()
    # Every OrgEvent published anywhere in the process (agents, graph
    # nodes, memory writes) must reach SSE subscribers on *this* loop --
    # see events/bus.py's module docstring for why this bind is required.
    event_bus.bind_loop(asyncio.get_running_loop())
    
    # Start OS Kernel background intelligence loop
    kernel = get_kernel()
    kernel.start_background_intelligence()
    
    yield
    
    # Stop OS Kernel background intelligence loop
    kernel.stop_background_intelligence()
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


_PROVIDER_MODEL = {
    "anthropic": lambda: settings.anthropic_model,
    "nvidia": lambda: settings.nvidia_model,
    "openai_compat": lambda: settings.openai_compat_model,
}


@app.get("/health")
def health() -> dict:
    model_for = _PROVIDER_MODEL.get(settings.llm_provider)
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "model": model_for() if model_for else "demo",
    }


class SignupRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str


_MIN_PASSWORD_LENGTH = 8


@app.post("/auth/signup", response_model=AuthResponse, status_code=201)
def signup(request: SignupRequest) -> AuthResponse:
    username = request.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="username is required")
    if len(request.password) < _MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400, detail=f"password must be at least {_MIN_PASSWORD_LENGTH} characters"
        )
    try:
        token = app.state.auth.signup(username, request.password)
    except UsernameTaken:
        raise HTTPException(status_code=409, detail="username already taken") from None
    return AuthResponse(token=token)


@app.post("/auth/login", response_model=AuthResponse)
def login(request: LoginRequest) -> AuthResponse:
    try:
        token = app.state.auth.login(request.username.strip(), request.password)
    except InvalidCredentials:
        raise HTTPException(status_code=401, detail="invalid username or password") from None
    return AuthResponse(token=token)


def get_current_user(authorization: str = Header(default="")) -> User:
    """FastAPI dependency gating every operator-facing endpoint below.
    Deliberately not applied to /health (frontend liveness check, no
    sensitive data) or /events/stream -- the browser's native EventSource
    cannot attach custom headers, so that stream stays unauthenticated, same
    trust level as /health (read-only mission telemetry, no secrets)."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    user = app.state.auth.get_user_for_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    return user


@app.post("/admin/reload-config")
def reload_config(user: User = Depends(get_current_user)) -> dict:
    """Re-reads `.env`/the process environment into the live `settings`
    object so a changed LLM provider or API key takes effect on the very
    next agent call, no restart needed. `ResilientLLMClient` already
    triggers this automatically on a failed call (see llm/resilient.py) --
    this endpoint is for reloading proactively, e.g. right after editing
    `.env` and before the current provider actually fails."""
    settings.reload()
    model_for = _PROVIDER_MODEL.get(settings.llm_provider)
    return {
        "status": "reloaded",
        "llm_provider": settings.llm_provider,
        "model": model_for() if model_for else "demo",
    }


@app.get("/agents")
def list_agents(user: User = Depends(get_current_user)) -> list[dict]:
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
        app.state.orchestrator.run(
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
def create_project(
    request: GoalRequest, user: User = Depends(get_current_user)
) -> StartProjectResponse:
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


def _resume_mission_in_background(project_id: str) -> None:
    try:
        app.state.orchestrator.resume(
            project_id,
            long_term=app.state.long_term,
            semantic=app.state.semantic,
            memory=app.state.memory,
        )
    except KeyError:
        # Raced with another resume click that got there first; that other
        # resume is now running this mission, so nothing to do.
        logger.info("mission %s was no longer resumable when the thread started", project_id)
    except MissionCancelled:
        pass  # run_organization already published workflow_cancelled
    except Exception:
        # A resume that fails again publishes workflow_failed (with
        # resumable=true) exactly like the original failure -- the operator
        # can fix .env again and press Resume again.
        logger.exception("resumed mission %s failed", project_id)


@app.post("/projects/{project_id}/resume", status_code=202)
def resume_project(project_id: str, user: User = Depends(get_current_user)) -> dict:
    """Resume a failed mission on the same project after the operator fixed
    the LLM provider/key in .env. Re-reads config, then continues the
    mission's checkpointed graph from its last completed node -- finished
    research/product/engineering stages are not re-run or re-billed."""
    if resumable_goal(project_id) is None:
        raise HTTPException(
            status_code=404,
            detail="no resumable mission with that id (not failed, or the server restarted)",
        )
    cancellation.register(project_id)
    threading.Thread(
        target=_resume_mission_in_background,
        args=(project_id,),
        daemon=True,
    ).start()
    return {"status": "resuming", "project_id": project_id}


@app.post("/projects/{project_id}/cancel")
def cancel_project(project_id: str, user: User = Depends(get_current_user)) -> dict:
    if not cancellation.request_cancel(project_id):
        raise HTTPException(status_code=404, detail="no running mission with that id")
    return {"status": "cancel_requested"}


@app.get("/projects")
def list_projects(limit: int = 50, user: User = Depends(get_current_user)) -> list[dict]:
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
def search_projects(
    q: str, top_k: int = 5, user: User = Depends(get_current_user)
) -> list[dict]:
    return app.state.semantic.search_similar(q, top_k=top_k)


@app.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, user: User = Depends(get_current_user)) -> ProjectResponse:
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
def list_project_files(project_id: str, user: User = Depends(get_current_user)) -> list[str]:
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
def list_memory_entries(limit: int = 50, user: User = Depends(get_current_user)) -> list[dict]:
    """Durable organizational memory: research findings, risks, and (later)
    architectural decisions recorded per run -- see memory/recording.py and
    ARCHITECTURE.md roadmap item #4. List-only, matching MemoryService's
    deliberately CRUD-only surface (no filtering/relevance ranking yet)."""
    entries = app.state.memory.list_entries(limit=limit)
    return [entry.model_dump(mode="json") for entry in entries]


@app.get("/digital-twin")
def get_digital_twin_state(user: User = Depends(get_current_user)) -> dict:
    """The read-only state of the living market model maintained by the OS kernel."""
    twin = get_digital_twin()
    return twin.model_dump(mode="json")


@app.get("/execution-logs")
def list_execution_logs(limit: int = 100, user: User = Depends(get_current_user)) -> list[dict]:
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


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


_CHAT_SYSTEM_PROMPT = (
    "You are the memory assistant for an AI software organization. Answer "
    "the operator's question briefly, using only the organizational memory "
    "context provided below -- do not invent projects or facts not present "
    "in it. If the question asks you to build, code, implement, or design "
    "something, do not attempt it: tell the operator to use \"Start "
    "Project\" instead, since that runs the full multi-agent research/"
    "product/engineering pipeline this chat does not have access to."
)


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user: User = Depends(get_current_user)) -> ChatResponse:
    """The Brain page's casual-question path: one direct LLM call grounded
    in real semantic-memory search results, not the 11-node mission graph.
    Reuses the exact same `search_similar` GET /projects/search already
    calls -- the "brain" here is real data (past projects' goals/summaries),
    not a fabricated always-on background process."""
    hits = app.state.semantic.search_similar(request.message, top_k=5)
    context = (
        "\n".join(f"- {hit['goal']}: {hit['summary']}" for hit in hits if hit.get("summary"))
        or "No related past projects found in memory."
    )
    llm = build_default_llm()
    reply = llm.complete(
        system=_CHAT_SYSTEM_PROMPT,
        user=f"Organizational memory (most relevant past projects):\n{context}\n\n"
        f"Operator question: {request.message}",
        max_tokens=1024,
    )
    return ChatResponse(reply=reply)


# ---------------------------------------------------------------------------
# Executive Business OS -- companies, metrics, approvals, briefing, assistant
# ---------------------------------------------------------------------------


class CompanyCreateRequest(BaseModel):
    name: str
    description: str = ""
    industry: str = ""
    stage: str = "operating"
    website: str = ""


@app.get("/companies")
def list_companies(user: User = Depends(get_current_user)) -> list[dict]:
    """Every company JARVIS operates for the founder (TradeW is seeded)."""
    return [c.model_dump(mode="json") for c in app.state.business.list_companies()]


@app.post("/companies", status_code=201)
def create_company(request: CompanyCreateRequest, user: User = Depends(get_current_user)) -> dict:
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="company name is required")
    company = app.state.business.create_company(
        Company(
            name=name,
            description=request.description,
            industry=request.industry,
            stage=request.stage,
            website=request.website,
        )
    )
    return company.model_dump(mode="json")


class MetricsRequest(BaseModel):
    mrr: float = 0.0
    revenue_this_month: float = 0.0
    customers: int = 0
    new_customers_this_month: int = 0
    churned_customers_this_month: int = 0
    active_users: int = 0
    support_open_tickets: int = 0
    marketing_spend_this_month: float = 0.0
    sales_pipeline_value: float = 0.0
    cash_balance: float = 0.0
    burn_rate_monthly: float = 0.0
    notes: str = ""


@app.get("/companies/{company_id}/metrics")
def list_company_metrics(
    company_id: str, limit: int = 12, user: User = Depends(get_current_user)
) -> list[dict]:
    """Metric snapshots for one company, newest first ([0] = current state)."""
    if app.state.business.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="unknown company")
    return [
        s.model_dump(mode="json") for s in app.state.business.list_metrics(company_id, limit=limit)
    ]


@app.post("/companies/{company_id}/metrics", status_code=201)
def record_company_metrics(
    company_id: str, request: MetricsRequest, user: User = Depends(get_current_user)
) -> dict:
    if app.state.business.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="unknown company")
    snapshot = app.state.business.record_metrics(
        BusinessMetricSnapshot(company_id=company_id, **request.model_dump())
    )
    return snapshot.model_dump(mode="json")


class MilestoneCreateRequest(BaseModel):
    title: str
    detail: str = ""
    owner_agent: str = "Chief of Staff"
    stage_target: str = ""


class MilestoneStatusRequest(BaseModel):
    status: str  # todo | in_progress | done | blocked
    blocker: str = ""


@app.get("/companies/{company_id}/milestones")
def list_milestones(company_id: str, user: User = Depends(get_current_user)) -> list[dict]:
    """The company's path to its next stage. For a pre-revenue company this,
    not the metrics grid, is what the dashboard shows."""
    if app.state.business.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="unknown company")
    return [m.model_dump(mode="json") for m in app.state.business.list_milestones(company_id)]


@app.post("/companies/{company_id}/milestones", status_code=201)
def create_milestone(
    company_id: str, request: MilestoneCreateRequest, user: User = Depends(get_current_user)
) -> dict:
    company = app.state.business.get_company(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="unknown company")
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="milestone title is required")
    milestone = app.state.business.create_milestone(
        Milestone(
            company_id=company_id,
            title=title,
            detail=request.detail,
            owner_agent=request.owner_agent,
            stage_target=request.stage_target or (next_stage(company.stage) or company.stage),
        )
    )
    return milestone.model_dump(mode="json")


@app.post("/companies/{company_id}/milestones/{milestone_id}/status")
def set_milestone_status(
    company_id: str,
    milestone_id: str,
    request: MilestoneStatusRequest,
    user: User = Depends(get_current_user),
) -> dict:
    try:
        milestone = app.state.business.set_milestone_status(
            milestone_id, request.status, request.blocker
        )
    except ValueError:
        raise HTTPException(
            status_code=400, detail="status must be todo, in_progress, done, or blocked"
        ) from None
    if milestone is None:
        raise HTTPException(status_code=404, detail="unknown milestone")
    return milestone.model_dump(mode="json")


@app.post("/companies/{company_id}/launch-plan")
def generate_launch_plan(company_id: str, user: User = Depends(get_current_user)) -> dict:
    """The Chief of Staff plans how to get this company to its next stage,
    and the resulting milestones are persisted. This is JARVIS's answer for a
    company with no revenue yet: a plan to build one, not a report on one.
    Milestones already done or in progress are preserved."""
    company = app.state.business.get_company(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="unknown company")
    target = next_stage(company.stage)
    if target is None:
        raise HTTPException(status_code=400, detail=f"{company.name} is already at the final stage")

    context = app.state.business.snapshot_for_briefing()
    chief = ChiefOfStaffAgent(build_default_llm(), long_term=app.state.long_term)
    plan = chief.launch_plan(company.name, target, context)
    saved = app.state.business.replace_milestones(
        company_id,
        [
            Milestone(
                company_id=company_id,
                title=item.title,
                detail=item.detail,
                owner_agent=item.owner_agent,
                stage_target=target,
            )
            for item in plan.milestones
        ],
    )
    return {
        "target_stage": target,
        "current_stage_assessment": plan.current_stage_assessment,
        "critical_path": plan.critical_path,
        "confidence": plan.confidence,
        "milestones": [m.model_dump(mode="json") for m in saved],
    }


class ApprovalCreateRequest(BaseModel):
    title: str
    detail: str = ""
    company_id: str | None = None
    requested_by: str = "Founder"


class ApprovalDecisionRequest(BaseModel):
    decision: str  # "approved" | "rejected"


@app.get("/approvals")
def list_approvals(
    status: str | None = "pending", limit: int = 50, user: User = Depends(get_current_user)
) -> list[dict]:
    return [
        a.model_dump(mode="json")
        for a in app.state.business.list_approvals(status=status or None, limit=limit)
    ]


@app.post("/approvals", status_code=201)
def create_approval(
    request: ApprovalCreateRequest, user: User = Depends(get_current_user)
) -> dict:
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="approval title is required")
    approval = app.state.business.create_approval(
        Approval(
            title=title,
            detail=request.detail,
            company_id=request.company_id,
            requested_by=request.requested_by,
        )
    )
    return approval.model_dump(mode="json")


@app.post("/approvals/{approval_id}/decision")
def decide_approval(
    approval_id: str, request: ApprovalDecisionRequest, user: User = Depends(get_current_user)
) -> dict:
    try:
        approval = app.state.business.decide_approval(approval_id, request.decision)
    except ValueError:
        raise HTTPException(
            status_code=400, detail="decision must be 'approved' or 'rejected'"
        ) from None
    if approval is None:
        raise HTTPException(status_code=404, detail="unknown approval")
    return approval.model_dump(mode="json")


@app.post("/briefing")
def generate_briefing(user: User = Depends(get_current_user)) -> dict:
    """The Chief of Staff composes today's executive briefing from the real
    company snapshot (latest metrics + pending approvals). POST, not GET --
    each call is a fresh LLM synthesis, not a cached read."""
    context = app.state.business.snapshot_for_briefing()
    chief = ChiefOfStaffAgent(build_default_llm(), long_term=app.state.long_term)
    briefing = chief.briefing(context)
    return briefing.model_dump(mode="json")


class AssistantRequest(BaseModel):
    message: str
    history: list[ConversationTurn] = []


@app.post("/assistant")
def assistant(request: AssistantRequest, user: User = Depends(get_current_user)) -> dict:
    """The voice-first Executive Assistant: one conversational turn grounded
    in the live business snapshot, semantic memory of past work, and the
    conversation so far (sent back by the client each turn)."""
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    context = app.state.business.snapshot_for_briefing()
    hits = app.state.semantic.search_similar(message, top_k=3)
    memory_context = "\n".join(
        f"- {hit['goal']}: {hit['summary']}" for hit in hits if hit.get("summary")
    )
    if memory_context:
        context = f"{context}\n\nRelevant organizational memory:\n{memory_context}"
    # Client-supplied history wins (it has the freshest turns); a client
    # with none (new device, cleared session) falls back to the persisted
    # conversation so JARVIS still remembers.
    history = request.history or app.state.business.recent_turns(limit=12)
    ea = ExecutiveAssistantAgent(build_default_llm(), long_term=app.state.long_term)
    reply = ea.converse(message, context, history=history)
    app.state.business.save_turn(ConversationTurn(who="founder", text=message))
    app.state.business.save_turn(ConversationTurn(who="jarvis", text=reply.reply))
    return reply.model_dump(mode="json")


@app.get("/assistant/history")
def assistant_history(limit: int = 30, user: User = Depends(get_current_user)) -> list[dict]:
    """The persisted founder <-> JARVIS conversation tail, oldest first --
    the frontend restores its transcript from this on load."""
    return [t.model_dump(mode="json") for t in app.state.business.recent_turns(limit=limit)]


@app.post("/assistant/greet")
def assistant_greet(user: User = Depends(get_current_user)) -> dict:
    """JARVIS's spoken greeting when the founder opens the app -- grounded
    in the live company snapshot and the recent conversation, so it can
    pick up where things left off."""
    context = app.state.business.snapshot_for_briefing()
    recent = app.state.business.recent_turns(limit=6)
    if recent:
        transcript = "\n".join(
            f"{'Founder' if turn.who == 'founder' else 'JARVIS'}: {turn.text}" for turn in recent
        )
        context = f"{context}\n\nRecent conversation (pick up where this left off):\n{transcript}"
    ea = ExecutiveAssistantAgent(build_default_llm(), long_term=app.state.long_term)
    greeting = ea.greet(context)
    app.state.business.save_turn(ConversationTurn(who="jarvis", text=greeting.reply))
    return greeting.model_dump(mode="json")
