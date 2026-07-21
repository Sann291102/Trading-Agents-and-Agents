from aio.domains.market.models import OptionChainDomain

class QuantitativeEngine:
    
    @staticmethod
    def calculate_pcr(chain: OptionChainDomain) -> float:
        total_put_oi = sum(strike.put_oi for strike in chain.strikes)
        total_call_oi = sum(strike.call_oi for strike in chain.strikes)
        
        if total_call_oi == 0:
            return 1.0 # Fallback
            
        return round(total_put_oi / total_call_oi, 4)

    @staticmethod
    def calculate_max_pain(chain: OptionChainDomain) -> float:
        pain_profile = {}
        for eval_strike in chain.strikes:
            total_pain = 0.0
            for strike in chain.strikes:
                # Call writers lose if spot > strike
                if eval_strike.strike_price > strike.strike_price:
                    total_pain += (eval_strike.strike_price - strike.strike_price) * strike.call_oi
                # Put writers lose if spot < strike
                if eval_strike.strike_price < strike.strike_price:
                    total_pain += (strike.strike_price - eval_strike.strike_price) * strike.put_oi
            pain_profile[eval_strike.strike_price] = total_pain
            
        if not pain_profile:
            return chain.spot_price
            
        # Max pain is the strike where total pain is minimum
        min_pain_strike = min(pain_profile, key=pain_profile.get)
        return min_pain_strike
