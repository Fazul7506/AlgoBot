from .base import BaseStrategy

class ScalpingStrategy(BaseStrategy):
    name='scalping'.title()
    slug='scalping'
    category='Scalping'
    description='Built-in scalping strategy using market data and indicator context only.'
    default_parameters={'lookback': 20, 'stake': 1, 'risk_reward': 2}
    def generate_signal(self):
        trend=self.indicator_data.get('trend') or self.market_data.get('trend')
        rsi=self.indicator_data.get('rsi')
        if rsi is not None:
            if rsi < 30: return 'BUY'
            if rsi > 70: return 'SELL'
        if trend in ('up','UPTREND','bullish'): return 'BUY'
        if trend in ('down','DOWNTREND','bearish'): return 'SELL'
        return 'HOLD'
