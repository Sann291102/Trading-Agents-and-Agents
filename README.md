# JARVIS: Market Intelligence OS

JARVIS is a production-ready AI Operating System specifically tailored for Market Intelligence within the TradeW ecosystem. Built on top of a resilient LangGraph orchestration engine, JARVIS replaces generic autonomous agents with a specialized **Market Intelligence Division** focused on the Indian Stock Market.

JARVIS is designed to act as an institutional-grade intelligence platform that can:
- **Plan & Reason:** Break down complex market inquiries into distinct research tasks.
- **Execute in Parallel:** Coordinate specialized agents (Index, Live Market, Psychology, Institutional Flow, Macro, Memory) to gather and synthesize data concurrently.
- **Learn & Persist:** Transform raw facts into a living Knowledge Graph and persist structured insights into an Obsidian Knowledge Vault.
- **Act Observably:** Expose its entire thinking process, memory retrieval, confidence levels, and agent communications through a dynamic Mission Control UI.

## Architecture

JARVIS builds upon the original AIO (AI Organization) architecture. It retains the core execution engine (LangGraph, long-term/semantic memory, events, and logging) but introduces a new paradigm for intelligence gathering. 

### Core Components
- **Market Director (CEO):** Orchestrates the pipeline and reviews final output.
- **Research Planner:** Analyzes the core goal and assigns tasks to specialists before any searching occurs.
- **Market Intelligence Division:**
  - `Index Research Agent`
  - `Live Market Context Agent`
  - `Market Psychology Agent`
  - `Institutional Flow Agent`
  - `Macro Research Agent`
  - `Market Memory Agent`
  - `Research Validation Agent`
- **Knowledge Engine:** Converts raw data into concepts, relationships, and actionable insights.
- **Obsidian Brain:** Persistent, locally-stored markdown knowledge base with automated backlinking.

*(Note: The legacy AIO agents—Executive, Product Manager, Backend Lead, etc.—have been preserved in `src/aio/agents/legacy/` for future reuse).*

## Requirements

- Python 3.11+
- Docker (for Postgres) — optional; you can also point `DATABASE_URL` at a local SQLite file and run with no Docker at all.
- An Anthropic API key (or `LLM_PROVIDER=demo` for cost-free local runs).

## Setup

```bash
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run the tests

Tests use an in-memory SQLite DB (for both structured and vector memory) plus a fake LLM client, so they don't need Docker or an API key:

```bash
PYTHONPATH=src pytest tests/ -v
```

## Run it locally

```bash
./scripts/run_dev.sh
```

This starts Postgres via Docker Compose and runs the API with auto-reload at `http://localhost:8000`. Interactive API docs are at `http://localhost:8000/docs`.

## Project Layout

```
src/aio/
  agents/          
    market_intelligence/  # JARVIS Market Intelligence Agents
    legacy/               # Original AIO Agents
  models/          Pydantic contracts for intelligence reports
  observability/   ExecutionMetrics
  llm/             Anthropic client wrapper
  memory/          Short-term, long-term (Postgres), semantic (SQL vector search)
  orchestration/   LangGraph StateGraph wiring the agents together
  api/             FastAPI gateway
  db/              SQLAlchemy models
tests/             pytest suite
```
