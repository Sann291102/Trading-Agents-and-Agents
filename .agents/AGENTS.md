# PROJECT CONSTITUTION

This document is the highest authority in the repository. Every implementation decision must follow these rules.

## RULE 1 — Never Break Working Code
Never delete working functionality. Never perform destructive rewrites. Prefer incremental migrations. Maintain backwards compatibility whenever practical.

## RULE 2 — Architecture First
Every feature must fit into the existing architecture. Never implement shortcuts that bypass
• Executive Brain
• Service Bus
• Market Intelligence Core
• Memory System
• Domain Layer
• Knowledge Graph
If a feature requires bypassing the architecture, improve the architecture instead.

## RULE 3 — One Source Of Truth
Every concept exists only once. Avoid duplicate logic, duplicate calculations, duplicate memory, duplicate providers. Centralize reusable functionality.

## RULE 4 — Observable Intelligence
Every important action should be observable. Users should always be able to see: which agent is running, what it is doing, what tools it is using, what memory it is reading, what knowledge it created, what event it published, why it made a decision. No black boxes.

## RULE 5 — Explain Before Answering
Every quantitative output must include: Value, Meaning, Confidence, Historical Context, Reasoning, Sources. No isolated numbers.

## RULE 6 — Knowledge Is Permanent
Knowledge is permanent. Memory is experience. Context is temporary. Never confuse these layers. Everything learned should strengthen the Knowledge Graph.

## RULE 7 — Event Driven
Components never communicate directly unless absolutely necessary. Communication should happen through the Service Bus. This includes Agents, Memory, Knowledge Graph, Mission Control, Digital Twin, Plugins, TradeW, Sentinel, Browser, Obsidian.

## RULE 8 — Plugin First
Every new capability should be designed so it can eventually become a plugin. Avoid hardcoded dependencies. Prefer interfaces over implementations.

## RULE 9 — UI Mirrors Intelligence
Mission Control is not a dashboard. Mission Control is the operating console. Users must see Thinking, Planning, Research, Reasoning, Memory, Knowledge, Events, Digital Twin, Provider Health, Background Tasks, Agent Health, Plugin Health. Everything happening inside the system.

## RULE 10 — Documentation Equals Code
Whenever code changes, update: README, Architecture, Roadmap, API, Agents, Memory, Plugins, Changelog, Developer Documentation. No undocumented features.

## RULE 11 — Test Before Completion
No task is complete until: ✓ Tests pass ✓ Build passes ✓ Documentation updated ✓ UI updated ✓ Memory integrated ✓ Events published correctly ✓ No regressions.

## RULE 12 — Vertical Slice First
Never build infrastructure without proving it through a working feature. Every architectural improvement should immediately enable a real capability. Workflow: Architecture -> Implementation -> Integration -> Validation -> Documentation -> Next Vertical Slice. Never spend weeks building infrastructure that is not exercised by working functionality.

## RULE 13 — TradeW Compatibility
Every architectural decision should consider future integration with TradeW, Sentinel, Backtesting, Paper Trading, Risk Engine, Portfolio Intelligence, Research Engine. The architecture must remain reusable across the TradeW ecosystem.

## RULE 14 — Executive Brain Owns The System
The Executive Brain is the operating system kernel. It owns Planning, Scheduling, Delegation, Context, Quality Control, Recovery, Continuous Intelligence, Workflow. Everything else is a service that supports the Executive Brain.

## DEFINITION OF DONE
A milestone is complete only when: ✓ Architecture remains coherent ✓ Feature works end-to-end ✓ Mission Control visualizes it ✓ Memory stores it ✓ Knowledge Graph connects it ✓ Documentation explains it ✓ Tests verify it ✓ Future roadmap is updated.
