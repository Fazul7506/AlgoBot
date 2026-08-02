from decimal import Decimal
from apps.strategies.constants import SIGNAL_TYPES

class BaseStrategy:
    name='Base Strategy'; slug='base'; category='AI Hybrid Strategies'; version='1.0.0'; description='Base strategy contract'; author='AlgoBot'
    default_parameters={'stake': 1, 'lookback': 20}
    def __init__(self, configuration=None, market_data=None, indicator_data=None):
        self.configuration=configuration; self.market_data=market_data or {}; self.indicator_data=indicator_data or {}; self.initialized=False
    def initialize(self): self.initialized=True; return True
    def validate(self): return True
    def analyze_market(self): return {'trend': self.indicator_data.get('trend','neutral'), 'volatility': self.indicator_data.get('volatility',0)}
    def generate_signal(self): return 'HOLD'
    def calculate_confidence(self):
        score=50
        if self.indicator_data.get('agreement'): score += int(self.indicator_data.get('agreement',0))*10
        if self.indicator_data.get('trend_strength'): score += min(20, int(self.indicator_data.get('trend_strength',0)))
        return max(0,min(100,score))
    def calculate_stop_loss(self): return self._price_delta(-0.01)
    def calculate_take_profit(self): return self._price_delta(0.02)
    def calculate_position_size(self): return Decimal(str(getattr(self.configuration,'parameters',{}).get('stake',1) if self.configuration else 1))
    def execute(self):
        signal=self.generate_signal(); confidence=self.calculate_confidence()
        if signal not in SIGNAL_TYPES: signal='HOLD'
        return {'signal': signal, 'confidence': confidence, 'entry_price': self.market_data.get('price'), 'stop_loss': self.calculate_stop_loss(), 'take_profit': self.calculate_take_profit(), 'position_size': str(self.calculate_position_size())}
    def shutdown(self): self.initialized=False; return True
    def _price_delta(self, pct):
        price=self.market_data.get('price') or self.market_data.get('close')
        return None if price is None else Decimal(str(price)) * (Decimal('1') + Decimal(str(pct)))
