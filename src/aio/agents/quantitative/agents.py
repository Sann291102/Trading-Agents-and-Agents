import json
from aio.agents.base import Agent
from aio.core.providers.mock_provider import MockMarketProvider
from aio.core.quantitative.engine import QuantitativeEngine
from aio.core.reasoning.engine import ReasoningEngine

class OptionChainMathAgent(Agent):
    role = "Option Chain Mathematics"
    department = "Market Quantitative Intelligence"
    system_prompt = "You calculate option chain math and derive meaning from the numbers."

    def execute(self, goal: str, symbol: str = "NIFTY") -> dict:
        # 1. Fetch Data
        provider = MockMarketProvider()
        
        import asyncio
        loop = asyncio.get_event_loop()
        chain_resp = loop.run_until_complete(provider.get_option_chain(symbol, None))
        
        # 2. Compute
        pcr = QuantitativeEngine.calculate_pcr(chain_resp.data)
        max_pain = QuantitativeEngine.calculate_max_pain(chain_resp.data)
        
        # 3. Reason
        reasoned_pcr = ReasoningEngine.reason_about_pcr(pcr)
        reasoned_max_pain = ReasoningEngine.reason_about_max_pain(max_pain, chain_resp.data.spot_price)
        
        return {
            "symbol": symbol,
            "pcr": reasoned_pcr.model_dump(),
            "max_pain": reasoned_max_pain.model_dump(),
            "confidence": min(reasoned_pcr.confidence, reasoned_max_pain.confidence),
            "reasoning_summary": f"PCR is {reasoned_pcr.meaning} and Max Pain implies {reasoned_max_pain.meaning}."
        }

    def handoff(self, report: dict) -> dict:
        return {"option_chain_report": report}

class GreeksIntelligenceAgent(Agent):
    role = "Greeks Intelligence"
    department = "Market Quantitative Intelligence"
    system_prompt = "You calculate option Greeks and their implied positioning."
    
    def execute(self, goal: str, symbol: str = "NIFTY") -> dict:
        provider = MockMarketProvider()
        
        import asyncio
        loop = asyncio.get_event_loop()
        greeks_resp = loop.run_until_complete(provider.get_market_greeks(symbol))
        
        greeks_data = greeks_resp.data
        
        # Simplified reasoning
        gamma = greeks_data.atm_call_greeks.gamma
        if gamma > 0.005:
            meaning = "High Gamma Risk"
            reasoning = "High gamma indicates rapid delta changes. Option sellers face elevated risk."
        else:
            meaning = "Normal Gamma"
            reasoning = "Gamma is within normal historical ranges."
            
        return {
            "symbol": symbol,
            "atm_call_gamma": gamma,
            "meaning": meaning,
            "reasoning": reasoning,
            "confidence": 0.88,
            "reasoning_summary": meaning
        }
        
    def handoff(self, report: dict) -> dict:
        return {"greeks_report": report}
