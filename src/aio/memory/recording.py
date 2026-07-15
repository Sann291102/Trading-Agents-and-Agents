"""Derive durable organizational MemoryEntry rows from a completed run.

This is roadmap item #4, *step 1* (see ARCHITECTURE.md): the Organizational
Memory Foundation (`MemoryService`) is CRUD-only and, until now, nothing in
the pipeline wrote to it. This module is the first writer. After a run
completes, it records:

- the merged research report as a ``RESEARCH_FINDING`` entry, and
- the report's identified risks as a single consolidated ``RISK`` entry,

both carrying the research report's *own* ``confidence`` -- so no confidence
value is fabricated.

``ARCHITECTURAL_DECISION`` recording (the roadmap's second named example)
deliberately waits until the Backend Lead produces a structured output with
a real confidence field. Its tech plan is currently free text logged with
``confidence=None`` (see ``Agent.run_logged`` / ``BackendLeadAgent``), and
this module records only entries whose confidence is a genuine signal, never
a placeholder. Retrieval, filtering, and any knowledge-graph linking remain
out of scope here -- see ARCHITECTURE.md's roadmap for what layers on top.
"""

from __future__ import annotations

from aio.events.bus import OrgEvent, event_bus
from aio.memory.service import MemoryService
from aio.models.memory import MemoryEntry, MemoryMetadata, MemoryType
from aio.models.research import ResearchReport

# Entry summaries stay readable at a glance in the memory list/UI; the full
# nested research report is still persisted verbatim on the Project row
# (research_report_json), so nothing is lost by excerpting here.
_SUMMARY_LIMIT = 600
_TITLE_GOAL_LIMIT = 80


def _excerpt(text: str, limit: int = _SUMMARY_LIMIT) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def record_project_memory(
    service: MemoryService,
    research_report: ResearchReport | None,
    goal: str,
    project_id: str,
) -> list[MemoryEntry]:
    """Create and persist the durable memory entries a completed run yields.

    Returns the entries created (empty if there was no research report, e.g.
    a run that failed before research merge). Each created entry also emits a
    ``knowledge_added`` event so the live stream/frontend reflects it, mirroring
    how ``SemanticMemory.upsert_project`` already announces embedding writes.
    """
    if research_report is None:
        return []

    goal_label = _excerpt(goal, _TITLE_GOAL_LIMIT)
    entries: list[MemoryEntry] = [
        MemoryEntry(
            project_id=project_id,
            title=f"Research finding — {goal_label}",
            type=MemoryType.RESEARCH_FINDING,
            summary=_excerpt(
                f"{research_report.executive_summary}\n\n"
                f"Recommended direction: {research_report.recommended_direction}"
            ),
            department="Research",
            owner="Research Coordinator",
            confidence=research_report.confidence,
            metadata=MemoryMetadata(
                source_agent="Research Coordinator",
                tags=["research", "executive-summary"],
                extra={
                    "opportunities": research_report.opportunities,
                    "recommended_direction": research_report.recommended_direction,
                },
            ),
        )
    ]

    if research_report.risks:
        entries.append(
            MemoryEntry(
                project_id=project_id,
                title=f"Risks identified — {goal_label}",
                type=MemoryType.RISK,
                summary=_excerpt("; ".join(research_report.risks)),
                department="Research",
                owner="Research Coordinator",
                confidence=research_report.confidence,
                metadata=MemoryMetadata(
                    source_agent="Research Coordinator",
                    tags=["risk"],
                    extra={"risks": research_report.risks},
                ),
            )
        )

    for entry in entries:
        service.create_entry(entry)
        event_bus.publish(
            OrgEvent(
                type="knowledge_added",
                department="Research",
                project_id=project_id,
                confidence=entry.confidence,
                message=(
                    f"Recorded {entry.type.value.replace('_', ' ')} "
                    f"to organizational memory: {entry.title}"
                ),
            )
        )

    return entries
