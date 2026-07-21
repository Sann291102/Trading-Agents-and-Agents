# JARVIS Market Intelligence OS - Internal Roadmap

This document serves as the permanent internal roadmap for the transformation and evolution of the JARVIS AI Operating System.

## Current State

- **Current Architecture:** Transitioning from generic AIO agents to the Market Intelligence Division. Existing LangGraph orchestration and Postgres memory systems are being preserved and adapted.
- **Current Milestone:** Milestone 1 (Core Market Intelligence & Research Planner)
- **Current Sprint:** Setup legacy archiving and scaffold Market Intelligence agents and Pydantic models.
- **Current Blockers:** None.
- **Current Technical Debt:** None currently identified. Old agents need to be properly isolated into a `legacy` module without breaking imports in test files or the `graph.py` fallback if applicable.
- **Current Next Task:** Archive legacy agents and update imports.

## Milestones

### Milestone 1: Core Market Intelligence & Research Planner (IN PROGRESS)
- [x] Establish the `market_intelligence/` agent division and `legacy/` division.
- [ ] Create the **Market Director** (new Executive node) and **Research Planner**.
- [ ] Implement specialist agents: Index Research, Live Market Context, Market Psychology, Institutional Flow, Macro Research, Market Memory, and Research Validation.
- [ ] Update LangGraph to route through the Research Planner and new agents.

### Milestone 2: JARVIS Browser & External Adapters
- Implement autonomous research tools with strict priority: Brave Search API -> Playwright -> Direct APIs -> Manual scraping.
- Build unified adapter interface for financial data (NSE, BSE, Screener, TradingView, Yahoo Finance, etc.).

### Milestone 3: Obsidian Brain Integration
- Direct filesystem markdown writing for Obsidian as the permanent knowledge repository.
- Automatically generate structured notes with backlinks connecting into the vault graph.

### Milestone 4: Knowledge Engine & Market Memory
- Build the pipeline to convert raw information into intelligence (Facts -> Concepts -> Relationships -> Knowledge Graph -> Memory).
- Teach Market Memory to learn patterns and regimes.

### Milestone 5: Mission Control UI
- Overhaul frontend for observable internal state (Real-time progress, Thinking timeline, Live DAG).

### Milestone 6: Live Knowledge Graph & Memory Visualization
- Implement interactive D3/Three.js visualizations for memory growth and relationships.

### Milestone 7: TradeW Integration
- APIs and pipelines for feeding JARVIS intelligence into TradeW.

### Milestone 8: Autonomous Learning
- Self-improvement loops (prompt refinement, outcome evaluation).

### Milestone 9: Production Hardening
- CI/CD, Kubernetes, performance tuning, and security audits.
