# AI Organization (AIO) — vertical slice

A working, runnable slice of an autonomous AI organization: an **Executive
AI (CEO)** that delegates a business goal to a **Research & Planning**
department (Research Coordinator + Domain Expert, Market Research,
Competitor Intelligence, and Technical Research specialists running in
parallel), then to a **Product** department and an **Engineering**
department -- reviewing output at each stage and persisting every run to
long-term (Postgres) and semantic (vector search in the same database)
memory.

Product Manager cannot generate requirements from a bare goal -- it only
acts on an Executive-reviewed research report. No engineering work starts
before research has completed and been reviewed.

This is deliberately small — see [`ARCHITECTURE.md`](ARCHITECTURE.md) for
what's here, why, and the roadmap to the full multi-department vision.

## Requirements

- Python 3.11+
- Docker (for Postgres) — optional; you can also point `DATABASE_URL` at a
  local SQLite file and run with no Docker at all
- An Anthropic API key (or `LLM_PROVIDER=demo` for cost-free local runs)

## Setup

```bash
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run the tests

Tests use an in-memory SQLite DB (for both structured and vector memory)
plus a fake LLM client, so they don't need Docker or an API key:

```bash
PYTHONPATH=src pytest tests/ -v
```

## Run it locally

```bash
./scripts/run_dev.sh
```

This starts Postgres via Docker Compose (semantic/vector memory lives in the
same database now — no separate Qdrant service) and runs the API with
auto-reload at `http://localhost:8000`. Interactive API docs are at
`http://localhost:8000/docs`.

Or run everything (API included) in Docker:

```bash
docker compose up --build
```

## Use it

Submit a business goal to the organization. This runs the full pipeline --
CEO plan, four parallel research specialists, research merge, CEO research
review, Product Manager, Backend Lead, CEO final review -- and can take a
while since it's a dozen-plus sequential/parallel LLM calls:

```bash
curl -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -d '{"goal": "Launch a customer feedback widget for our SaaS dashboard"}'
```

The response includes the merged `research_report` (domain, market,
competitor, and technical findings plus an executive summary and
recommended direction), the `business_requirements` document (vision,
epics, user stories, roadmap, risks, success metrics) Product Manager
derived from it, Engineering's `tech_plan`, and the CEO's final
APPROVE/CHANGES `review`.

Fetch a past run:

```bash
curl http://localhost:8000/projects/<project_id>
```

Find similar past projects (semantic search over research executive summaries):

```bash
curl "http://localhost:8000/projects/search?q=feedback%20widget"
```

List recent agent execution logs (timing, confidence, errors, handoffs):

```bash
curl "http://localhost:8000/execution-logs?limit=50"
```

## Project layout

```
src/aio/
  agents/          Executive, Research Coordinator, 4 research specialists,
                    Product Manager, Backend Lead agent classes
  models/          Pydantic contracts (ResearchReport, BusinessRequirementsDocument, ...)
  observability/   ExecutionMetrics -- what Agent.run_logged records
  llm/             Anthropic client wrapper (the only wired LLM provider)
  memory/          short-term (in-process), long-term (Postgres), semantic (SQL vector search)
  orchestration/   LangGraph StateGraph wiring the agents together (with
                    parallel fan-out/fan-in over the 4 research agents)
  api/             FastAPI gateway
  db/               SQLAlchemy models
tests/              pytest suite (no network/Docker required)
docs/diagrams/       Mermaid flowchart, sequence, and class diagrams
```

## Extending

Adding a department = adding an `Agent` subclass in `src/aio/agents/` plus a
node/edge in `src/aio/orchestration/graph.py`. Nothing else in the stack
needs to change. See the roadmap in `ARCHITECTURE.md` for suggested next
additions (human approval loop, Design/QA/DevOps departments, knowledge
graph, more connectors).
