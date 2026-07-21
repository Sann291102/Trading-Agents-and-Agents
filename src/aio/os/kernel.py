import asyncio
from typing import Dict, Any, Callable, Awaitable

from aio.events.bus import event_bus, OrgEvent
from aio.os.digital_twin import get_digital_twin
from aio.core.providers.mock_provider import MockMarketProvider
from aio.core.quantitative.engine import QuantitativeEngine
from aio.core.reasoning.engine import ReasoningEngine

class ExecutiveBrain:
    """
    The OS Kernel. Owns orchestration, scheduling, continuous intelligence loops, and context.
    """
    def __init__(self):
        self.digital_twin = get_digital_twin()
        self.market_provider = MockMarketProvider()
        self._background_tasks = []
        self._is_running = False

    def start_background_intelligence(self):
        if not self._is_running:
            self._is_running = True
            task = asyncio.create_task(self._intelligence_loop())
            self._background_tasks.append(task)
            event_bus.publish(OrgEvent(type="os_started", message="Executive Brain started continuous intelligence loop."))

    def stop_background_intelligence(self):
        self._is_running = False
        for task in self._background_tasks:
            task.cancel()
        self._background_tasks.clear()
        event_bus.publish(OrgEvent(type="os_stopped", message="Executive Brain stopped continuous intelligence loop."))

    async def _intelligence_loop(self):
        """24/7 Background loop updating the digital twin."""
        while self._is_running:
            try:
                # 1. Fetch data
                chain_resp = await self.market_provider.get_option_chain("NIFTY", None)
                chain = chain_resp.data
                
                # 2. Compute math
                pcr_val = QuantitativeEngine.calculate_pcr(chain)
                max_pain_val = QuantitativeEngine.calculate_max_pain(chain)
                
                # 3. Apply reasoning
                # Hardcoded context for Phase 1 vertical slice
                context = "Expiry Tomorrow" 
                
                reasoned_pcr = ReasoningEngine.reason_about_pcr(pcr_val, context=context)
                reasoned_max_pain = ReasoningEngine.reason_about_max_pain(max_pain_val, chain.spot_price)
                
                # 4. Update Digital Twin
                self.digital_twin.update_state({
                    "pcr": reasoned_pcr,
                    "max_pain": reasoned_max_pain
                })
                
                event_bus.publish(OrgEvent(
                    type="digital_twin_updated", 
                    message=f"Digital Twin updated. PCR: {reasoned_pcr.value}, Max Pain: {reasoned_max_pain.value}"
                ))
                
            except Exception as e:
                event_bus.publish(OrgEvent(type="os_error", message=f"Intelligence loop error: {e}"))
                
            # Sleep before next update (short for Phase 1 testing)
            await asyncio.sleep(5)

# Global kernel singleton for Phase 1
_kernel = ExecutiveBrain()

def get_kernel() -> ExecutiveBrain:
    return _kernel
