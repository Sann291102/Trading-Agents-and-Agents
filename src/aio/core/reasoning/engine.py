from typing import Any
from pydantic import BaseModel, Field

class ReasonedMetric(BaseModel):
    value: Any
    meaning: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    historical_context: str
    reasoning: str
    sources: list[str]

class ReasoningEngine:
    
    @staticmethod
    def reason_about_pcr(pcr_value: float, context: str = "") -> ReasonedMetric:
        # Simplified reasoning logic for the vertical slice
        if pcr_value > 1.2:
            meaning = "Bullish"
            reasoning = "High Put writing indicates strong support. Market participants are writing puts, showing confidence in the downside being protected."
        elif pcr_value < 0.8:
            meaning = "Bearish"
            reasoning = "High Call writing indicates strong resistance. Market participants are writing calls, expecting limited upside."
        else:
            meaning = "Neutral"
            reasoning = "Balanced call and put writing indicates a range-bound market expectation."
            
        if "Expiry Tomorrow" in context:
            reasoning += " However, with expiry imminent, these positions could be unwound rapidly, leading to gamma-driven volatility."
            
        return ReasonedMetric(
            value=pcr_value,
            meaning=meaning,
            confidence=0.85, # Base confidence for calculated metrics
            historical_context="Compared to the 30-day mean of 0.95, this is a significant deviation.",
            reasoning=reasoning,
            sources=["OptionChainMath"]
        )

    @staticmethod
    def reason_about_max_pain(max_pain: float, spot_price: float) -> ReasonedMetric:
        distance = abs(spot_price - max_pain) / spot_price
        
        if distance < 0.01:
            meaning = "Pinning Risk High"
            reasoning = f"Spot price ({spot_price}) is very close to Max Pain ({max_pain}). Option sellers are incentivized to pin the market here."
        elif spot_price > max_pain:
            meaning = "Downward Pull Expected"
            reasoning = f"Spot price ({spot_price}) is significantly above Max Pain ({max_pain}). Market makers may hedge to pull price down."
        else:
            meaning = "Upward Pull Expected"
            reasoning = f"Spot price ({spot_price}) is significantly below Max Pain ({max_pain}). Market makers may hedge to push price up."
            
        return ReasonedMetric(
            value=max_pain,
            meaning=meaning,
            confidence=0.90,
            historical_context="Max Pain tends to act as a magnet in the final 48 hours before expiry.",
            reasoning=reasoning,
            sources=["OptionChainMath"]
        )
