"""Deterministic, zero-cost stand-in for AnthropicClient.

Used when `settings.llm_provider == "demo"`. This lets the *real*
orchestration graph, *real* agents, and *real* event bus be exercised
end-to-end -- and the frontend verified against genuinely live SSE events
-- without a paid Anthropic API key. Every agent call still happens, every
handoff/review/event is real; only the underlying text generation is
canned instead of a network call. Production deployments must leave
`LLM_PROVIDER` at "anthropic" (the default) in `.env`.

This is the same pattern already used for tests (see
tests/test_orchestration.py's FakeAnthropicClient) promoted to a
first-class, importable implementation because Phase 3 needs to trigger
real runs outside of pytest.
"""

from __future__ import annotations

import json
import re

from aio.agents.parsing import extract_role_from_system_prompt

_GOAL_RE = re.compile(r"Business goal:\s*\n(.+?)(?:\n\n|$)", re.DOTALL)


def _goal_snippet(user: str, limit: int = 80) -> str:
    match = _GOAL_RE.search(user)
    text = match.group(1).strip() if match else user.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _domain_expert(user: str) -> str:
    goal = _goal_snippet(user)
    return json.dumps(
        {
            "industry": "Software / SaaS",
            "terminology": ["MVP", "onboarding", "churn", "activation"],
            "business_workflows": ["user sign-up", "core task completion", "billing"],
            "compliance_concerns": ["data privacy (GDPR/CCPA)"],
            "industry_standards": ["OAuth2", "SOC 2"],
            "user_personas": ["primary end user", "team admin"],
            "business_constraints": ["small initial engineering team", "limited launch budget"],
            "kpis": ["activation rate", "weekly active users", "time to first value"],
            "pain_points": ["manual/slow existing workflow", "fragmented tooling"],
            "domain_risks": ["low adoption if onboarding friction is high"],
            "confidence": 0.74,
            "reasoning_summary": f"Derived from the stated goal: {goal!r}.",
        }
    )


def _market_research(user: str) -> str:
    goal = _goal_snippet(user)
    return json.dumps(
        {
            "target_users": ["early-stage teams", "operations-heavy small businesses"],
            "existing_products": ["incumbent generalist tools", "point solutions"],
            "market_size_estimate": "Sizable but fragmented; no dominant single incumbent",
            "pricing_landscape": "Per-seat SaaS, roughly $10-50/user/month",
            "customer_expectations": ["fast onboarding", "integrates with existing tools"],
            "emerging_trends": ["AI-assisted workflows", "usage-based pricing"],
            "technology_adoption": ["cloud-first", "mobile-secondary"],
            "confidence": 0.68,
            "reasoning_summary": f"Comparable-market sizing for: {goal!r}.",
        }
    )


def _competitor_intelligence(user: str) -> str:
    return json.dumps(
        {
            "competitors": [
                {
                    "name": "Incumbent A",
                    "features": ["core workflow", "basic reporting"],
                    "pricing": "mid-market SaaS contract",
                    "architecture": "monolithic, on-prem option",
                    "technology": "legacy stack",
                    "strengths": ["brand recognition", "large install base"],
                    "weaknesses": ["slow to ship", "dated UX"],
                    "differentiators": ["enterprise support contracts"],
                },
                {
                    "name": "Challenger B",
                    "features": ["modern UI", "API-first"],
                    "pricing": "usage-based",
                    "architecture": "cloud-native microservices",
                    "technology": "modern web stack",
                    "strengths": ["fast iteration", "developer-friendly"],
                    "weaknesses": ["smaller support org", "narrower feature set"],
                    "differentiators": ["strong API/integration story"],
                },
            ],
            "swot": {
                "strengths": ["can move faster than the incumbent"],
                "weaknesses": ["no existing brand recognition"],
                "opportunities": ["underserved segment ignored by both competitors"],
                "threats": ["challenger could expand into the same segment first"],
            },
            "feature_gaps": [
                {
                    "feature": "AI-assisted workflow",
                    "our_status": "planned",
                    "competitor_status": "partial",
                    "notes": "Meaningful differentiation window if shipped early.",
                }
            ],
            "confidence": 0.63,
            "reasoning_summary": "Based on typical incumbent-vs-challenger dynamics for this category.",
        }
    )


def _technical_research(user: str) -> str:
    return json.dumps(
        {
            "frameworks": ["FastAPI", "Next.js"],
            "cloud_services": ["managed Postgres", "object storage", "managed vector DB"],
            "architecture_patterns": ["modular monolith to start", "event-driven for async work"],
            "existing_apis": ["auth-as-a-service provider", "billing provider API"],
            "sdks": ["official SDKs for the auth/billing providers"],
            "integration_possibilities": ["Slack", "email", "webhook-based integrations"],
            "licensing_notes": ["prefer permissive OSS (MIT/Apache-2.0) for core dependencies"],
            "performance_benchmarks": ["typical API p95 latency target: under 300ms"],
            "confidence": 0.71,
            "reasoning_summary": "Standard, low-risk stack choices for a first release at this scale.",
        }
    )


def _research_coordinator_plan(user: str) -> str:
    return (
        "- Domain Expert: identify the industry, personas, and constraints\n"
        "- Market Research: size the market, map pricing and expectations\n"
        "- Competitor Intelligence: map competing products and find gaps\n"
        "- Technical Research: survey feasible frameworks and integrations"
    )


def _research_coordinator_merge(user: str) -> str:
    goal = _goal_snippet(user)
    return json.dumps(
        {
            "executive_summary": (
                f"Research supports pursuing '{goal}' as a focused first release "
                "targeting an underserved segment, differentiated on faster "
                "onboarding and an early AI-assisted workflow feature."
            ),
            "opportunities": [
                "underserved segment ignored by the largest incumbent",
                "differentiation window on AI-assisted workflow",
            ],
            "risks": [
                "adoption risk if onboarding friction is high",
                "challenger competitor could target the same segment first",
            ],
            "assumptions": [
                "target users will tolerate a narrower initial feature set for faster onboarding",
            ],
            "recommended_direction": (
                "Ship a focused MVP for the underserved segment, prioritizing "
                "onboarding speed and the AI-assisted workflow differentiator."
            ),
            "supporting_evidence": [
                "market sizing indicates no dominant single incumbent",
                "competitor feature-gap analysis shows AI-assisted workflow is only partially covered",
            ],
            "confidence": 0.72,
            "reasoning_summary": "Synthesized from domain, market, competitor, and technical findings.",
        }
    )


def _executive_review_research(user: str) -> str:
    return (
        "APPROVE. The research is internally consistent, confidence is "
        "acceptable across all four specialist reports, and the recommended "
        "direction is concrete enough for Product to act on."
    )


def _executive_plan(user: str) -> str:
    return (
        "- Research & Planning: investigate domain, market, competitors, and technical feasibility\n"
        "- Product: turn the approved research into a Business Requirements Document\n"
        "- Engineering: turn the requirements into a technical implementation plan"
    )


def _executive_final_review(user: str) -> str:
    return (
        "APPROVE. Requirements are grounded in the research findings and the "
        "technical plan is scoped appropriately for a first release."
    )


def _product_manager(user: str) -> str:
    goal = _goal_snippet(user)
    return json.dumps(
        {
            "vision": {
                "statement": f"Deliver a focused first release addressing: {goal}",
                "target_users": ["primary end user", "team admin"],
                "value_proposition": "Faster time-to-value than existing incumbent tools",
            },
            "epics": [
                {
                    "title": "Onboarding & account setup",
                    "description": "Let a new user create an account and reach first value quickly.",
                    "user_stories": [
                        {
                            "as_a": "new user",
                            "i_want": "to create an account in under a minute",
                            "so_that": "I can start using the product immediately",
                            "acceptance_criteria": [
                                "email+password signup with inline validation",
                                "user reaches the core workflow within 2 screens",
                            ],
                        }
                    ],
                },
                {
                    "title": "Core workflow",
                    "description": "The primary task the product exists to support.",
                    "user_stories": [
                        {
                            "as_a": "user",
                            "i_want": "to complete the core workflow end to end",
                            "so_that": "I get the primary value of the product",
                            "acceptance_criteria": [
                                "core workflow completes without needing support docs",
                                "errors are shown inline with a clear next step",
                            ],
                        }
                    ],
                },
            ],
            "release_roadmap": [
                {
                    "name": "MVP",
                    "scope": "onboarding + core workflow",
                    "epics": ["Onboarding & account setup", "Core workflow"],
                }
            ],
            "sprint_suggestions": [
                "Sprint 1: onboarding + auth",
                "Sprint 2: core workflow end to end",
            ],
            "risk_register": [
                {
                    "description": "Onboarding friction reduces activation",
                    "likelihood": "medium",
                    "impact": "high",
                    "mitigation": "usability-test the signup flow before launch",
                }
            ],
            "success_metrics": [
                {
                    "name": "activation rate",
                    "target": "40% of signups reach core workflow completion",
                    "rationale": "matches comparable SaaS onboarding benchmarks",
                }
            ],
            "confidence": 0.7,
            "reasoning_summary": "Derived directly from the approved research report's recommended direction.",
        }
    )


def _backend_lead(user: str) -> str:
    return (
        "Architecture: modular monolith (FastAPI) behind an API gateway, "
        "managed Postgres for relational data, managed vector DB for search. "
        "Data model: users, accounts, core-workflow entities, audit log. "
        "Key endpoints: POST /accounts, POST /sessions, core-workflow CRUD "
        "endpoints. Risks: keep the core workflow's data model flexible "
        "since Product may iterate on it quickly after launch."
    )


_HANDLERS: dict[str, callable] = {
    "Domain Expert": _domain_expert,
    "Market Research Analyst": _market_research,
    "Competitor Intelligence Agent": _competitor_intelligence,
    "Technical Research Agent": _technical_research,
    "Product Manager": _product_manager,
    "Backend Lead": _backend_lead,
}


def _research_coordinator(user: str) -> str:
    if "research objectives" in user:
        return _research_coordinator_plan(user)
    return _research_coordinator_merge(user)


def _executive(user: str) -> str:
    if "execution plan" in user:
        return _executive_plan(user)
    if "APPROVE it for Product" in user:
        return _executive_review_research(user)
    return _executive_final_review(user)


def _queen_coordinator(user: str) -> str:
    """Canned SwarmPlan: a representative six-specialist squad. Roles must
    exist in ruflo_defs/manifest.json -- plan_swarm drops any that don't."""
    return json.dumps(
        {
            "assignments": [
                {
                    "role": "System Architect",
                    "task": "Produce the module-level architecture for the approved technical plan.",
                    "rationale": "Architecture first so implementers share one design.",
                },
                {
                    "role": "Backend API Developer",
                    "task": "Design the REST endpoints and request/response contracts.",
                    "rationale": "Core delivery surface of the technical plan.",
                },
                {
                    "role": "Database Specialist",
                    "task": "Design the relational schema and migration plan.",
                    "rationale": "Data model underpins every endpoint.",
                },
                {
                    "role": "API Docs Writer",
                    "task": "Draft the OpenAPI specification with JWT bearer security scheme.",
                    "rationale": "Swagger-first auth is a stated product requirement.",
                },
                {
                    "role": "Tester",
                    "task": "Write the test plan covering the critical user journeys.",
                    "rationale": "Validation gate needs explicit acceptance checks.",
                },
                {
                    "role": "Security Auditor",
                    "task": "Audit the planned auth flow and list required hardening steps.",
                    "rationale": "Auth handles credentials; audit before build, not after.",
                },
            ],
            "strategy": "architecture-first fan-out, quality gates in parallel",
            "confidence": 0.75,
            "reasoning_summary": "Squad chosen to cover design, build, data, docs, test, and security lanes of the tech plan.",
        }
    )


def _production_validator(user: str) -> str:
    return json.dumps(
        {
            "passed": True,
            "issues": [],
            "confidence": 0.8,
            "reasoning_summary": (
                "All specialist outputs are present, mutually consistent, and "
                "cover the technical plan's scope."
            ),
        }
    )


def _swarm_worker(role: str, user: str) -> str:
    """Generic canned deliverable for any other ruflo specialist."""
    return (
        f"[{role} — demo output]\n"
        f"Deliverable for the assigned task:\n{_goal_snippet(user, 120)}\n\n"
        "1. Reviewed the technical plan context relevant to this task.\n"
        "2. Produced the specialist work product described above.\n"
        "3. Flagged no blocking issues; ready for Production Validator review."
    )


def _code_integrator(user: str) -> str:
    goal = _goal_snippet(user, 60)
    return (
        "===FILE: app/page.tsx===\n"
        "export default function Page() {\n"
        "  return (\n"
        "    <main style={{ padding: 32, fontFamily: \"system-ui, sans-serif\" }}>\n"
        f"      <h1>Demo preview</h1>\n"
        f"      <p>Standing in for: {goal}</p>\n"
        "    </main>\n"
        "  );\n"
        "}\n"
        "===END===\n"
    )


def _market_director(user: str) -> str:
    return "APPROVE. Excellent synthesis."

def _research_planner(user: str) -> str:
    return json.dumps({
        "goal": _goal_snippet(user),
        "tasks": [
            {
                "agent_role": "Index Research Agent",
                "objective": "Analyze major indices",
                "required_outputs": ["Support levels", "Resistance levels"]
            }
        ],
        "target_sectors": ["IT", "Banking"],
        "target_indices": ["Nifty 50"],
        "confidence": 0.85,
        "reasoning_summary": "Derived from user goal."
    })

def _index_research(user: str) -> str:
    return json.dumps({
        "index_name": "Nifty 50",
        "current_status": "Bullish",
        "key_drivers": ["Banking sector rally"],
        "corporate_actions": [],
        "support_resistance_levels": {"support_1": 24000.0, "resistance_1": 25000.0},
        "confidence": 0.8,
        "reasoning_summary": "Mock index report."
    })

def _live_market(user: str) -> str:
    return json.dumps({
        "market_breadth": "positive",
        "option_chain_summary": "Support at 24500",
        "vix_status": "falling",
        "sector_rotation": ["IT to Banking"],
        "key_observations": ["High volume in midcaps"],
        "confidence": 0.75,
        "reasoning_summary": "Mock live market report."
    })

def _market_psychology(user: str) -> str:
    return json.dumps({
        "retail_sentiment": "Bullish",
        "institutional_sentiment": "Cautious",
        "fear_greed_index_proxy": 0.7,
        "dominant_narratives": ["Buy the dip"],
        "confidence": 0.7,
        "reasoning_summary": "Mock psychology report."
    })

def _institutional_flow(user: str) -> str:
    return json.dumps({
        "fii_activity": "Buy",
        "dii_activity": "Sell",
        "notable_block_deals": ["HDFC Bank"],
        "accumulation_distribution_zones": ["24000"],
        "confidence": 0.82,
        "reasoning_summary": "Mock flow report."
    })

def _macro_research(user: str) -> str:
    return json.dumps({
        "global_cues": ["US markets up"],
        "domestic_indicators": ["GDP growth strong"],
        "rbi_policy_stance": "Neutral",
        "currency_commodity_impact": "INR stable, oil falling",
        "confidence": 0.85,
        "reasoning_summary": "Mock macro report."
    })

def _market_memory(user: str) -> str:
    return json.dumps({
        "historical_similarities": ["2017 bull run"],
        "past_regimes": ["Low volatility bull"],
        "recurring_patterns": ["Pre-election rally"],
        "confidence": 0.77,
        "reasoning_summary": "Mock memory report."
    })

def _research_validation(user: str) -> str:
    return json.dumps({
        "executive_summary": "The market is in a bullish regime with strong FII buying.",
        "synthesis": "Target banking stocks on dips.",
        "key_risks": ["Global recession"],
        "actionable_insights": ["Accumulate banking stocks"],
        "confidence": 0.9,
        "reasoning_summary": "Mock validation report."
    })

_ROLE_HANDLERS: dict[str, callable] = {
    **_HANDLERS,
    "Research Coordinator": _research_coordinator,
    "JARVIS": _executive,
    "Queen Coordinator": _queen_coordinator,
    "Production Validator": _production_validator,
    "Code Integrator": _code_integrator,
    "Market Director": _market_director,
    "Research Planner": _research_planner,
    "Index Research Agent": _index_research,
    "Live Market Context Agent": _live_market,
    "Market Psychology Agent": _market_psychology,
    "Institutional Flow Agent": _institutional_flow,
    "Macro Research Agent": _macro_research,
    "Market Memory Agent": _market_memory,
    "Research Validation Agent": _research_validation,
}


def _chief_of_staff(user: str) -> str:
    return json.dumps(
        {
            "confidence": 0.8,
            "reasoning_summary": "Composed from the company snapshot provided in context.",
            "headline": "Business steady; one decision pending and metrics need a refresh.",
            "business_health": "stable",
            "summary": (
                "Operations are stable across the connected companies. The most "
                "recent metric snapshot is the source of truth for revenue and "
                "customers; keep it current so briefings stay grounded. Clear "
                "any pending approvals to unblock the teams."
            ),
            "priorities": [
                {
                    "title": "Decide pending approvals",
                    "why_now": "Teams are blocked until the founder decides",
                    "owner_agent": "Chief of Staff",
                    "impact": "high",
                },
                {
                    "title": "Record this month's metric snapshot",
                    "why_now": "Briefings degrade without fresh numbers",
                    "owner_agent": "Business Analyst",
                    "impact": "medium",
                },
            ],
            "risks": [
                {
                    "title": "Stale metrics hide churn or burn changes",
                    "severity": "medium",
                    "mitigation": "Monthly snapshot cadence owned by the Business Analyst",
                }
            ],
            "opportunities": ["Automate metric collection via connectors"],
        }
    )


def _executive_assistant_intent(user: str) -> str:
    """Demo stand-in for the act() path. Returns a real delegation when the
    founder's message sounds like an order, so demo mode exercises the whole
    execute-an-action loop rather than only the conversational branch."""
    said = user.rpartition("Founder says:")[2].strip() or user.strip()
    lowered = said.lower()
    orders = ("delegate", "have the", "ask the", "tell the", "get the", "scope", "draft")
    if any(word in lowered for word in orders):
        return json.dumps(
            {
                "reply": "On it — handing that to the Operations Director now.",
                "action": "delegate_to_agent",
                "params": {"agent_role": "Operations Director", "task": said[:200]},
                "suggested_actions": [],
            }
        )
    return json.dumps(
        {
            "reply": (
                "Here is where things stand, based on the current business "
                "snapshot. Want me to put someone on it?"
            ),
            "action": "",
            "params": {},
            "suggested_actions": ["Delegate the next milestone to its owner"],
        }
    )


def _executive_assistant(user: str) -> str:
    if "Greet the founder" in user:
        return json.dumps(
            {
                "reply": (
                    "Welcome back. I'm across the numbers and the desk is in "
                    "order — say the word and I'll pull up any company, or "
                    "compose today's briefing."
                ),
                "suggested_actions": [
                    "Generate today's executive briefing",
                    "Review pending approvals",
                ],
            }
        )
    return json.dumps(
        {
            "reply": (
                "Understood. Based on the current business snapshot, here is "
                "where things stand — and I've kept the conversation so far "
                "in mind. Anything specific you want me to hand to a director?"
            ),
            "suggested_actions": ["Ask the Business Analyst to dig into the latest metrics"],
        }
    )


def _launch_plan(user: str) -> str:
    return json.dumps(
        {
            "confidence": 0.72,
            "reasoning_summary": "Planned from the company's stated pre-launch state.",
            "current_stage_assessment": (
                "Pre-revenue and pre-launch: there is no product in front of users "
                "yet, so nothing can be measured. The only thing that matters is "
                "shortening the distance to a first working release."
            ),
            "critical_path": (
                "Cut scope to the one workflow a first user would pay for, ship it "
                "to a small private group, then convert that group."
            ),
            "milestones": [
                {
                    "title": "Define the single core workflow for v1",
                    "detail": "One user journey, written down, that the release must support end to end.",
                    "owner_agent": "Operations Director",
                },
                {
                    "title": "Ship a working private beta",
                    "detail": "That workflow running for real users, not a demo.",
                    "owner_agent": "Operations Director",
                },
                {
                    "title": "Recruit 10 design partners",
                    "detail": "Ten named people who agreed to use it and give feedback.",
                    "owner_agent": "Sales Director",
                },
                {
                    "title": "Decide launch pricing",
                    "detail": "A published price and what the first tier includes.",
                    "owner_agent": "Finance Manager",
                },
                {
                    "title": "Prepare the launch story",
                    "detail": "Positioning and channels ready for launch day.",
                    "owner_agent": "Marketing Director",
                },
            ],
        }
    )


def _business_agent_handler(system: str):
    """Business-roster prompts all open with 'You are the <role>' -- match
    on the raw system prompt so demo mode covers the whole Executive
    Business OS. Imported lazily for the same reason as ruflo_role_names."""
    from aio.agents.business import BUSINESS_AGENT_CLASSES

    for cls in BUSINESS_AGENT_CLASSES:
        if system.startswith(f"You are the {cls.role}"):
            if cls.role == "Chief of Staff" and "JSON schema" in system:
                return _launch_plan if "the plan, not" in system else _chief_of_staff
            if cls.role == "Executive Assistant" and "JSON schema" in system:
                # act() and converse()/greet() share a role but not a schema;
                # the capability menu only appears in the former's prompt.
                if "Capabilities you can run:" in system:
                    return _executive_assistant_intent
                return _executive_assistant
            return lambda user, role=cls.role: (
                f"[{role} — demo output]\n"
                f"Actioned: {_goal_snippet(user, 120)}\n"
                "Grounded in the business context provided; no blocking issues."
            )
    return None


class DemoAnthropicClient:
    def __init__(self, model: str | None = None) -> None:
        self.model = model or "demo"

    def complete(self, system: str, user: str, max_tokens: int = 2048) -> str:
        role = extract_role_from_system_prompt(system)
        handler = _ROLE_HANDLERS.get(role)
        if handler is not None:
            return handler(user)
        business_handler = _business_agent_handler(system)
        if business_handler is not None:
            return business_handler(user)
        # Any other ruflo-imported specialist gets the generic worker
        # deliverable. Imported lazily: aio.llm must stay importable
        # without the agents package (and vice versa) at module load.
        from aio.agents.ruflo_loader import ruflo_role_names

        if role in ruflo_role_names():
            return _swarm_worker(role, user)
        raise RuntimeError(f"DemoAnthropicClient has no canned response for role {role!r}")
