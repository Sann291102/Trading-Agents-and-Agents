from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

class StrikeData(BaseModel):
    strike_price: float
    call_oi: int
    put_oi: int
    call_volume: int
    put_volume: int
    call_iv: float
    put_iv: float
    call_ltp: float
    put_ltp: float

class OptionChainDomain(BaseModel):
    symbol: str
    expiry_date: datetime
    spot_price: float
    timestamp: datetime
    strikes: List[StrikeData]

class GreekData(BaseModel):
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    charm: float = 0.0
    vanna: float = 0.0
    vomma: float = 0.0

class MarketGreeksDomain(BaseModel):
    symbol: str
    timestamp: datetime
    atm_call_greeks: GreekData
    atm_put_greeks: GreekData
    gamma_exposure_profile: dict[str, float] = Field(default_factory=dict)
