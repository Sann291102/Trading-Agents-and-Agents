from __future__ import annotations

from aio.models.product import BusinessRequirementsDocument

from ..base import Agent


class BackendLeadAgent(Agent):
    """Engineering Division. Turns a Business Requirements Document into a
    technical plan. No engineering work starts before Product has produced
    a research-grounded BRD -- see the orchestration graph."""

    role = "Backend Lead"
    department = "Engineering"
    system_prompt = (
        "You are the Backend Lead of the Engineering department. Given a "
        "Business Requirements Document, produce a concise technical "
        "implementation plan: proposed architecture, data model, key API "
        "endpoints, and any notable risks or open questions. Do not write "
        "full source code, just enough detail that a team could start "
        "building from it."
    )

    def plan_implementation(self, requirements: BusinessRequirementsDocument) -> str:
        task = (
            f"Business Requirements Document:\n{requirements.model_dump_json()}\n\n"
            "Produce the technical plan now."
        )
        text, _ = self.run_logged(task, handoff_target="JARVIS")
        return text
