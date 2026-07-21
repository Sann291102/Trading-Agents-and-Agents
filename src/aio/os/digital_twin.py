from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

from aio.core.reasoning.engine import ReasonedMetric

class MarketState(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    pcr: Optional[ReasonedMetric] = None
    max_pain: Optional[ReasonedMetric] = None
    atm_iv: Optional[ReasonedMetric] = None
    market_breadth: Optional[ReasonedMetric] = None
    # Can be extended with Macro, Sentiment, Liquidity, etc.
    
class DigitalTwin(BaseModel):
    """
    The living model of the market's state. 
    Continuously updated by the OS Kernel's background intelligence loop.
    Read-only for external clients.
    """
    current_state: MarketState = Field(default_factory=MarketState)
    historical_states: list[MarketState] = Field(default_factory=list)
    
    def update_state(self, updates: dict[str, ReasonedMetric]):
        # Archive current state
        self.historical_states.append(self.current_state.model_copy(deep=True))
        if len(self.historical_states) > 100: # Keep recent history bounded in memory
            self.historical_states.pop(0)
            
        # Update current state
        new_state = self.current_state.model_copy(deep=True)
        new_state.timestamp = datetime.now(timezone.utc)
        
        for key, value in updates.items():
            if hasattr(new_state, key):
                setattr(new_state, key, value)
                
        self.current_state = new_state

# Global singleton for Phase 1 vertical slice (to be managed by OS Kernel)
_global_digital_twin = DigitalTwin()

def get_digital_twin() -> DigitalTwin:
    return _global_digital_twin
