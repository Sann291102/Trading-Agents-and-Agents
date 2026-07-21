import json
from aio.agents.base import Agent
from aio.agents.parsing import json_response_instruction, parse_json_response
from aio.models.market_intelligence import (
    IndexReport,
    LiveMarketContext,
    MarketPsychology,
    InstitutionalFlow,
    MacroContext,
    MarketMemoryContext,
    MarketIntelligenceReport
)

class ResearchValidationAgent(Agent):
    role = "Research Validation Agent"
    department = "Market Intelligence"
    output_schema = MarketIntelligenceReport

    def synthesize_and_validate(
        self,
        goal: str,
        index: IndexReport,
        live: LiveMarketContext,
        psychology: MarketPsychology,
        flow: InstitutionalFlow,
        macro: MacroContext,
        memory: MarketMemoryContext
    ) -> MarketIntelligenceReport:
        self.system_prompt = (
            f"You are the {self.role} in the {self.department}. "
            "Your objective is to synthesize the parallel research outputs into a single, cohesive "
            "Market Intelligence Report. You must cross-validate findings, resolve contradictions, "
            "and produce an executive summary and actionable insights.\n\n"
            "Return ONLY the top-level synthesis, key risks, and actionable insights. "
            "The individual reports will be attached programmatically.\n\n"
            f"{json_response_instruction(MarketIntelligenceReport)}"
        )
        
        user = (
            f"Goal: {goal}\n\n"
            f"--- Index Report ---\n{index.model_dump_json(indent=2)}\n\n"
            f"--- Live Market ---\n{live.model_dump_json(indent=2)}\n\n"
            f"--- Psychology ---\n{psychology.model_dump_json(indent=2)}\n\n"
            f"--- Flow ---\n{flow.model_dump_json(indent=2)}\n\n"
            f"--- Macro ---\n{macro.model_dump_json(indent=2)}\n\n"
            f"--- Memory ---\n{memory.model_dump_json(indent=2)}\n\n"
        )
        
        # Parse it properly
        report = self.run_logged_json(user, MarketIntelligenceReport, handoff_target="Market Director")
        report.index_context = index
        report.live_market_context = live
        report.psychology_context = psychology
        report.institutional_flow = flow
        report.macro_context = macro
        report.memory_context = memory
        
        return report
