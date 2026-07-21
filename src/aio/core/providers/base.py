from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field

from aio.domains.market.models import OptionChainDomain, MarketGreeksDomain

class ProviderQualityScore(BaseModel):
    freshness_ms: int
    confidence: float = Field(..., ge=0.0, le=1.0)
    source: str
    stage: str = Field(..., description="Stage 1: Mock, Stage 2: Sandbox, Stage 3: Live, Stage 4: Consensus")

class ProviderResponse(BaseModel):
    quality: ProviderQualityScore
    data: BaseModel

class BaseMarketProvider(ABC):
    
    @abstractmethod
    async def get_option_chain(self, symbol: str, expiry_date: datetime) -> ProviderResponse:
        pass
        
    @abstractmethod
    async def get_market_greeks(self, symbol: str) -> ProviderResponse:
        pass
