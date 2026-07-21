import asyncio
from datetime import datetime, timezone
import random

from aio.core.providers.base import BaseMarketProvider, ProviderResponse, ProviderQualityScore
from aio.domains.market.models import OptionChainDomain, StrikeData, MarketGreeksDomain, GreekData

class MockMarketProvider(BaseMarketProvider):
    
    async def get_option_chain(self, symbol: str, expiry_date: datetime) -> ProviderResponse:
        await asyncio.sleep(0.1) # Simulate network call
        spot = 24500.0 if symbol == "NIFTY" else 52000.0
        
        strikes = []
        for i in range(-5, 6):
            strike_price = spot + (i * 100)
            strikes.append(StrikeData(
                strike_price=strike_price,
                call_oi=random.randint(50000, 2000000),
                put_oi=random.randint(50000, 2000000),
                call_volume=random.randint(10000, 500000),
                put_volume=random.randint(10000, 500000),
                call_iv=random.uniform(0.12, 0.25),
                put_iv=random.uniform(0.12, 0.25),
                call_ltp=random.uniform(10.0, 500.0),
                put_ltp=random.uniform(10.0, 500.0),
            ))
            
        domain_data = OptionChainDomain(
            symbol=symbol,
            expiry_date=expiry_date,
            spot_price=spot,
            timestamp=datetime.now(timezone.utc),
            strikes=strikes
        )
        
        return ProviderResponse(
            quality=ProviderQualityScore(
                freshness_ms=0,
                confidence=1.0,
                source="MockDataProvider",
                stage="Stage 1: Mock"
            ),
            data=domain_data
        )

    async def get_market_greeks(self, symbol: str) -> ProviderResponse:
        await asyncio.sleep(0.1)
        
        domain_data = MarketGreeksDomain(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            atm_call_greeks=GreekData(
                delta=0.52,
                gamma=0.003,
                theta=-15.4,
                vega=12.2,
                rho=5.1
            ),
            atm_put_greeks=GreekData(
                delta=-0.48,
                gamma=0.003,
                theta=-14.8,
                vega=12.2,
                rho=-5.2
            ),
            gamma_exposure_profile={
                "24000": 1500000.0,
                "24500": 3000000.0,
                "25000": -2000000.0
            }
        )
        
        return ProviderResponse(
            quality=ProviderQualityScore(
                freshness_ms=0,
                confidence=1.0,
                source="MockDataProvider",
                stage="Stage 1: Mock"
            ),
            data=domain_data
        )
