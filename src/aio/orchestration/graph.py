"""The organization's orchestration graph.

CEO -> Research Coordinator -> [Domain Expert, Market Research, Competitor
Intelligence, Technical Research] (parallel) -> Research Coordinator merge
-> CEO research review -> Product Manager -> Backend Lead -> CEO final
review, wired as a LangGraph StateGraph.

The four research nodes have no edges between each other, only shared
in-edges from `research_plan` and shared out-edges to `research_merge` --
LangGraph's Pregel executor runs same-superstep nodes concurrently and
`research_merge` only fires once all four of its predecessors have
completed, giving real parallel fan-out/fan-in without any extra
synchronization code here.

Product Manager cannot run before `research_merge` and `ceo_research_review`
have produced and approved a ResearchReport -- there is no edge into
`product` from anywhere else, so this is a structural guarantee, not just a
convention. (Branching on `research_approved` to loop back into research on
CHANGES is deliberately not implemented yet -- see ARCHITECTURE.md roadmap;
`research_approved` is computed and stored precisely so that gate can be
added without touching anything upstream of it.)

Every node also publishes coarse organizational events (task_delegated,
research_complete, review_requested, approval_granted/changes_requested) to
the shared event bus -- these are the "the organization is handing work
between departments" moments the frontend's live workflow view keys off,
distinct from the finer-grained agent_started/agent_finished events that
`Agent.run_logged` already publishes for every individual LLM call.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import TypedDict

from aio.orchestration.base import OrchestratorInterface

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from aio.agents import (
    RUFLO_AGENT_CLASSES,
    BackendLeadAgent,
    CodeIntegratorAgent,
    CompetitorIntelligenceAgent,
    DomainExpertAgent,
    ExecutiveAgent,
    MarketResearchAgent,
    ProductManagerAgent,
    ResearchCoordinatorAgent,
    TechnicalResearchAgent,
)
from aio.agents.base import Agent
from aio.events.bus import OrgEvent, event_bus
from aio.integrations.n8n import N8nClient
from aio.llm import build_default_llm
from aio.llm.anthropic_client import AnthropicClient
from aio.memory.long_term import LongTermMemory
from aio.memory.recording import record_project_memory
from aio.memory.semantic import SemanticMemory
from aio.memory.service import MemoryService
from aio.models.product import BusinessRequirementsDocument
from aio.models.preview import GeneratedApp
from aio.models.research import (
    CompetitorMatrix,
    DomainKnowledgeReport,
    MarketResearchReport,
    ResearchReport,
    TechnicalResearchReport,
)
from aio.models.swarm import SwarmPlan, SwarmTaskResult, SwarmValidation
from aio.observability.context import current_project_id
from aio.orchestration import cancellation
from aio.orchestration.cancellation import MissionCancelled
from aio.orchestration.swarm import execute_swarm, plan_swarm, validate_swarm
from aio.preview import preview_manager

logger = logging.getLogger("aio.orchestration.graph")

# One process-wide checkpointer: LangGraph saves the mission state after
# every completed node under thread_id=project_id, which is what makes a
# failed mission resumable from where it stopped (rather than restarted
# from scratch) after the operator fixes the LLM provider/key in .env.
# In-memory on purpose -- a resume only makes sense while the API process
# that watched the mission fail is still alive; a durable (SQLite)
# checkpointer is the upgrade path if that ever changes.
_CHECKPOINTER = MemorySaver()

# project_id -> goal for missions that failed mid-run and can be resumed.
# Only failures land here (not cancellations -- those are deliberate).
_RESUMABLE: dict[str, str] = {}


def resumable_goal(project_id: str) -> str | None:
    """The goal of a failed, resumable mission, or None if that id isn't
    resumable (unknown, still running, cancelled, or already completed)."""
    return _RESUMABLE.get(project_id)


class OrgState(TypedDict, total=False):
    goal: str
    project_id: str
    ceo_plan: str
    research_plan: str
    domain_report: DomainKnowledgeReport
    market_report: MarketResearchReport
    competitor_matrix: CompetitorMatrix
    technical_report: TechnicalResearchReport
    research_report: ResearchReport
    research_review: str
    research_approved: bool
    business_requirements: BusinessRequirementsDocument
    tech_plan: str
    review: str
    approved: bool
    swarm_plan: SwarmPlan
    swarm_results: list[SwarmTaskResult]
    swarm_validation: SwarmValidation
    generated_app: GeneratedApp
    preview_url: str
    preview_error: str


def _emit(type_: str, *, department: str | None = None, message: str, **extra) -> None:
    event_bus.publish(
        OrgEvent(
            type=type_,
            department=department,
            project_id=current_project_id.get(),
            message=message,
            **extra,
        )
    )


def _excerpt(text: str, limit: int = 160) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_legacy_graph(
    ceo: ExecutiveAgent,
    research_coordinator: ResearchCoordinatorAgent,
    domain_expert: DomainExpertAgent,
    market_research: MarketResearchAgent,
    competitor_intelligence: CompetitorIntelligenceAgent,
    technical_research: TechnicalResearchAgent,
    product_manager: ProductManagerAgent,
    backend_lead: BackendLeadAgent,
    code_integrator: CodeIntegratorAgent,
    swarm_squad: dict[str, Agent] | None = None,
):
    graph = StateGraph(OrgState)

    def ceo_plan_node(state: OrgState) -> dict:
        ceo_plan = ceo.plan(state["goal"])
        _emit(
            "task_delegated",
            department="Executive",
            message="JARVIS delegated the goal to the Research & Planning department",
        )
        return {"ceo_plan": ceo_plan}

    def research_plan_node(state: OrgState) -> dict:
        return {"research_plan": research_coordinator.plan(state["goal"])}

    def domain_node(state: OrgState) -> dict:
        return domain_expert.handoff(domain_expert.execute(state["goal"]))

    def market_node(state: OrgState) -> dict:
        return market_research.handoff(market_research.execute(state["goal"]))

    def competitor_node(state: OrgState) -> dict:
        return competitor_intelligence.handoff(competitor_intelligence.execute(state["goal"]))

    def technical_node(state: OrgState) -> dict:
        return technical_research.handoff(technical_research.execute(state["goal"]))

    def research_merge_node(state: OrgState) -> dict:
        report = research_coordinator.execute(
            state["goal"],
            state["domain_report"],
            state["market_report"],
            state["competitor_matrix"],
            state["technical_report"],
        )
        _emit(
            "research_complete",
            department="Research",
            message=_excerpt(report.executive_summary),
            confidence=report.confidence,
        )
        _emit(
            "review_requested",
            department="Research",
            message="Research Coordinator requested Executive review of the merged research report",
        )
        return research_coordinator.handoff(report)

    def ceo_research_review_node(state: OrgState) -> dict:
        review = ceo.review_research(state["goal"], state["research_report"])
        approved = review.strip().upper().startswith("APPROVE")
        _emit(
            "approval_granted" if approved else "changes_requested",
            department="Executive",
            message=_excerpt(review),
        )
        if approved:
            _emit(
                "task_delegated",
                department="Executive",
                message="JARVIS approved the research and delegated requirements-writing to Product",
            )
        return {"research_review": review, "research_approved": approved}

    def product_node(state: OrgState) -> dict:
        brd = product_manager.execute(state["goal"], state["research_report"])
        _emit(
            "task_delegated",
            department="Product",
            message="Product Manager delegated implementation planning to Backend Lead",
        )
        return product_manager.handoff(brd)

    def backend_node(state: OrgState) -> dict:
        tech_plan = backend_lead.plan_implementation(state["business_requirements"])
        _emit(
            "review_requested",
            department="Engineering",
            message="Backend Lead requested final Executive review of the technical plan",
        )
        return {"tech_plan": tech_plan}

    def ceo_review_node(state: OrgState) -> dict:
        requirements_summary = state["business_requirements"].model_dump_json()
        review = ceo.review(state["goal"], requirements_summary, state["tech_plan"])
        approved = review.strip().upper().startswith("APPROVE")
        _emit(
            "approval_granted" if approved else "changes_requested",
            department="Executive",
            message=_excerpt(review),
        )
        return {"review": review, "approved": approved}

    def swarm_plan_node(state: OrgState) -> dict:
        plan = plan_swarm(
            swarm_squad["Queen Coordinator"], state["goal"], state["tech_plan"], swarm_squad
        )
        _emit(
            "task_delegated",
            department="Swarm Command",
            message=(
                f"Queen Coordinator dispatched {len(plan.assignments)} assignments "
                f"to the engineering swarm: "
                + ", ".join(a.role for a in plan.assignments)
            ),
            confidence=plan.confidence,
        )
        return {"swarm_plan": plan}

    def swarm_execute_node(state: OrgState) -> dict:
        results = execute_swarm(swarm_squad, state["swarm_plan"])
        failed = [r.role for r in results if r.error]
        _emit(
            "review_requested",
            department="Swarm Command",
            message=(
                f"Engineering swarm finished {len(results)} tasks"
                + (f" ({len(failed)} failed: {', '.join(failed)})" if failed else "")
                + " -- requesting Production Validator review"
            ),
        )
        return {"swarm_results": results}

    def swarm_validate_node(state: OrgState) -> dict:
        validation = validate_swarm(
            swarm_squad["Production Validator"],
            state["goal"],
            state["tech_plan"],
            state["swarm_results"],
        )
        _emit(
            "approval_granted" if validation.passed else "changes_requested",
            department="Quality",
            message=(
                "Production Validator passed the swarm output"
                if validation.passed
                else "Production Validator flagged issues: "
                + _excerpt("; ".join(validation.issues))
            ),
            confidence=validation.confidence,
        )
        return {"swarm_validation": validation}

    graph.add_node("ceo_plan", ceo_plan_node)
    graph.add_node("research_plan", research_plan_node)
    graph.add_node("domain", domain_node)
    graph.add_node("market", market_node)
    graph.add_node("competitor", competitor_node)
    graph.add_node("technical", technical_node)
    graph.add_node("research_merge", research_merge_node)
    graph.add_node("ceo_research_review", ceo_research_review_node)
    graph.add_node("product", product_node)
    graph.add_node("backend", backend_node)
    graph.add_node("ceo_review", ceo_review_node)

    graph.set_entry_point("ceo_plan")
    graph.add_edge("ceo_plan", "research_plan")

    for research_node in ("domain", "market", "competitor", "technical"):
        graph.add_edge("research_plan", research_node)
        graph.add_edge(research_node, "research_merge")

    graph.add_edge("research_merge", "ceo_research_review")
    graph.add_edge("ceo_research_review", "product")
    graph.add_edge("product", "backend")
    graph.add_edge("backend", "ceo_review")

    def preview_node(state: OrgState) -> dict:
        # Never raises: a preview failure must not take down the rest of
        # the mission response (tech plan, swarm results, etc. are already
        # decided by this point and must still reach the caller).
        _emit(
            "deployment_started",
            department="Engineering",
            message="Code Integrator is building a live preview from the swarm's output",
        )
        try:
            generated_app = code_integrator.execute(
                state["goal"], state["tech_plan"], state["swarm_results"]
            )
            info = preview_manager.start(state["project_id"], generated_app)
        except MissionCancelled:
            # Must propagate, not be folded into "preview unavailable" --
            # this is the operator stopping the whole mission, not a preview
            # build failure (see the generic except below).
            raise
        except Exception as exc:
            _emit(
                "deployment_finished",
                department="Engineering",
                message=f"Live preview unavailable: {_excerpt(str(exc))}",
                payload={"preview_error": str(exc)},
            )
            return {"preview_error": str(exc)}

        if info.status == "ready":
            _emit(
                "deployment_finished",
                department="Engineering",
                message=f"Live preview ready at {info.url}",
                payload={"preview_url": info.url},
            )
            return {"generated_app": generated_app, "preview_url": info.url}

        _emit(
            "deployment_finished",
            department="Engineering",
            message=f"Live preview unavailable: {_excerpt(info.error or 'unknown error')}",
            payload={"preview_error": info.error},
        )
        return {"generated_app": generated_app, "preview_error": info.error}

    if swarm_squad is None:
        graph.add_edge("ceo_review", END)
    else:
        # The swarm only runs on an approved tech plan -- a structural gate,
        # like Product's dependence on approved research above.
        graph.add_node("swarm_plan", swarm_plan_node)
        graph.add_node("swarm_execute", swarm_execute_node)
        graph.add_node("swarm_validate", swarm_validate_node)
        graph.add_node("preview", preview_node)
        graph.add_conditional_edges(
            "ceo_review",
            lambda state: "swarm_plan" if state.get("approved") else END,
            {"swarm_plan": "swarm_plan", END: END},
        )
        graph.add_edge("swarm_plan", "swarm_execute")
        graph.add_edge("swarm_execute", "swarm_validate")
        graph.add_edge("swarm_validate", "preview")
        graph.add_edge("preview", END)

    return graph.compile(checkpointer=_CHECKPOINTER)


def run_legacy_organization(
    goal: str,
    llm: AnthropicClient | None = None,
    long_term: LongTermMemory | None = None,
    semantic: SemanticMemory | None = None,
    memory: MemoryService | None = None,
    persist: bool = True,
    swarm: bool = True,
    project_id: str | None = None,
    _resume: bool = False,
) -> OrgState:
    llm = llm or build_default_llm()
    if persist:
        long_term = long_term or LongTermMemory()
        # Idempotent -- agents log execution metrics as they run, during the
        # graph invocation below, not just at the final save_project call,
        # so the schema must exist before any node executes.
        long_term.init_schema()

    # Generated up front (not just when saving at the end) so every event
    # published during the run -- by any agent, on any node -- can carry
    # the correct project_id from its very first "agent_started" onward.
    # See observability/context.py for why this is a contextvar rather than
    # a parameter threaded through every agent method. A caller that already
    # knows the id it wants (api/main.py -- generated before this function
    # is even called, so it can hand the id back to the frontend immediately
    # instead of waiting for the whole mission to finish) can pass it in.
    project_id = project_id or str(uuid.uuid4())
    token = current_project_id.set(project_id)
    cancellation.register(project_id)

    ceo = ExecutiveAgent(llm, long_term=long_term)
    research_coordinator = ResearchCoordinatorAgent(llm, long_term=long_term)
    domain_expert = DomainExpertAgent(llm, long_term=long_term)
    market_research = MarketResearchAgent(llm, long_term=long_term)
    competitor_intelligence = CompetitorIntelligenceAgent(llm, long_term=long_term)
    technical_research = TechnicalResearchAgent(llm, long_term=long_term)
    product_manager = ProductManagerAgent(llm, long_term=long_term)
    backend_lead = BackendLeadAgent(llm, long_term=long_term)
    code_integrator = CodeIntegratorAgent(llm, long_term=long_term)

    # The full ruflo squad is instantiated per run (agents are cheap
    # wrappers around the shared llm client); which of them actually get
    # work is the Queen Coordinator's runtime decision in swarm_plan_node.
    swarm_squad = (
        {role: cls(llm, long_term=long_term) for role, cls in RUFLO_AGENT_CLASSES.items()}
        if swarm
        else None
    )

    app = build_legacy_graph(
        ceo,
        research_coordinator,
        domain_expert,
        market_research,
        competitor_intelligence,
        technical_research,
        product_manager,
        backend_lead,
        code_integrator,
        swarm_squad=swarm_squad,
    )

    # thread_id keys this run's checkpoints; on resume, invoking with None
    # input tells LangGraph to continue the existing thread from its last
    # saved checkpoint instead of starting over at the entry point.
    config = {"configurable": {"thread_id": project_id}}
    graph_input = None if _resume else {"goal": goal, "project_id": project_id}

    try:
        result: OrgState = app.invoke(graph_input, config)
    except MissionCancelled:
        _emit("workflow_cancelled", message="Mission stopped by operator request")
        raise
    except Exception as exc:
        # The checkpoint written after the last *completed* node survives in
        # _CHECKPOINTER, so the operator can fix the provider/key in .env and
        # resume this exact mission -- see resume_organization.
        _RESUMABLE[project_id] = goal
        _emit(
            "workflow_failed",
            message=_excerpt(f"Workflow failed: {exc}"),
            payload={"resumable": True},
        )
        raise
    finally:
        current_project_id.reset(token)
        cancellation.clear(project_id)

    result["project_id"] = project_id
    _RESUMABLE.pop(project_id, None)

    if persist:
        semantic = semantic or SemanticMemory()
        research_report = result.get("research_report")
        business_requirements = result.get("business_requirements")
        swarm_plan = result.get("swarm_plan")
        swarm_results = result.get("swarm_results")
        swarm_validation = result.get("swarm_validation")
        long_term.save_project(
            id=project_id,
            goal=goal,
            research_report_json=research_report.model_dump_json() if research_report else "",
            research_review=result.get("research_review", ""),
            research_approved=result.get("research_approved", False),
            business_requirements_json=(
                business_requirements.model_dump_json() if business_requirements else ""
            ),
            tech_plan=result.get("tech_plan", ""),
            review=result.get("review", ""),
            approved=result.get("approved", False),
            swarm_plan_json=swarm_plan.model_dump_json() if swarm_plan else "",
            swarm_results_json=(
                json.dumps([r.model_dump(mode="json") for r in swarm_results])
                if swarm_results
                else ""
            ),
            swarm_validation_json=swarm_validation.model_dump_json() if swarm_validation else "",
            preview_url=result.get("preview_url", ""),
            preview_error=result.get("preview_error", ""),
        )
        summary = research_report.executive_summary if research_report else result.get("review", "")
        semantic.upsert_project(project_id=project_id, goal=goal, summary=summary)

        # Roadmap item #4, step 1: record durable organizational memory
        # entries (research findings, risks) from this run. Same DB as
        # long_term; init_schema is idempotent and only adds the
        # memory_entries table. A recording failure must not lose the run
        # that already succeeded and persisted above.
        memory = memory or MemoryService()
        memory.init_schema()
        try:
            record_project_memory(memory, research_report, goal, project_id)
        except Exception:  # noqa: BLE001 -- best-effort, non-critical write
            logger.exception("recording organizational memory failed for project %s", project_id)

        # Fire a best-effort n8n webhook so an operator-built workflow can
        # react to mission completion -- a no-op unless N8N_BASE_URL is set
        # (see integrations/n8n.py). Failure here must never affect a
        # mission that already completed and persisted above.
        N8nClient().notify_mission_complete(
            {
                "project_id": project_id,
                "goal": goal,
                "approved": result.get("approved", False),
                "research_approved": result.get("research_approved", False),
                "preview_url": result.get("preview_url", ""),
            }
        )

    return result


def resume_organization(project_id: str, **kwargs) -> OrgState:
    """Resume a failed mission from its last completed node.

    Re-reads `.env` first so a provider/API-key change the operator just
    made is what the rebuilt agents run on, then re-invokes the mission's
    checkpoint thread -- completed nodes are not re-executed; the failed
    node retries on the fresh provider. Raises KeyError if the id isn't
    resumable (unknown, still running, cancelled, or already completed).
    `kwargs` pass through to run_legacy_organization (memory backends, swarm flag)
    so the API can hand in the same app.state services it uses for new runs.
    """
    goal = _RESUMABLE.get(project_id)
    if goal is None:
        raise KeyError(f"no resumable mission with id {project_id}")

    from aio.config import settings

    settings.reload()
    _emit_for_project(
        project_id,
        "task_delegated",
        department="Executive",
        message="JARVIS is resuming the mission from its last completed step",
    )
    return run_legacy_organization(goal, project_id=project_id, _resume=True, **kwargs)


def _emit_for_project(project_id: str, type_: str, **kwargs) -> None:
    """Like _emit, but for callers running before current_project_id is set
    (resume_organization emits its resuming notice prior to entering
    run_legacy_organization, which is what binds the contextvar)."""
    event_bus.publish(OrgEvent(type=type_, project_id=project_id, **kwargs))

class LangGraphOrchestrator(OrchestratorInterface):
    def run(self, goal: str, **kwargs) -> OrgState:
        return run_legacy_organization(goal, **kwargs)

    def resume(self, project_id: str, **kwargs) -> OrgState:
        return resume_organization(project_id, **kwargs)
