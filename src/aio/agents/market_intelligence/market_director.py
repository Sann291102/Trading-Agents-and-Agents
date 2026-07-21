import json
from aio.agents.base import Agent
from aio.models.market_intelligence import MarketIntelligenceReport

class MarketDirectorAgent(Agent):
    role = "Market Director"
    department = "Market Intelligence"

    def review_synthesis(self, goal: str, report: MarketIntelligenceReport) -> str:
        self.system_prompt = (
            f"You are the {self.role}, the leader of the {self.department}. "
            "Your job is to review the synthesized market intelligence report and ensure it "
            "directly answers the original user goal with high confidence and actionable insights."
        )

        user = (
            f"Goal: {goal}\n\n"
            f"Synthesized Report:\n{report.model_dump_json(indent=2)}\n\n"
            "Respond with either 'APPROVE' if the intelligence is actionable and complete, "
            "or a detailed 'CHANGES: <reason>' if specific areas need further investigation."
        )

        # run_logged returns (text, metrics)
        response_text, _ = self.run_logged(user)
        
        if response_text.strip().upper().startswith("APPROVE"):
            return "APPROVE"
            
        return response_text
