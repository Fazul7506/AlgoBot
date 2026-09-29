from decimal import Decimal

from apps.strategies.constants import SIGNAL_TYPES
from apps.strategies.criteria import CriteriaEngine


class BaseStrategy:
    name = 'Base Strategy'
    slug = 'base'
    category = 'AI Hybrid Strategies'
    version = '1.0.0'
    description = 'Base strategy contract'
    author = 'AlgoBot'
    default_parameters = {'stake': 1, 'lookback': 20}

    def __init__(self, configuration=None, market_data=None, indicator_data=None):
        self.configuration = configuration
        self.market_data = market_data or {}
        self.indicator_data = indicator_data or {}
        self.initialized = False
        self.criteria_result = {'passed': True, 'reasons': []}

    def initialize(self):
        self.initialized = True
        return True

    def validate(self):
        if not self.initialized:
            raise ValueError('Strategy must be initialized before validation')
        return True

    def analyze_market(self):
        return {
            'trend': self.indicator_data.get('trend', 'neutral'),
            'volatility': self.indicator_data.get('volatility', 0),
        }

    def generate_signal(self):
        # The base contract has no strategy evidence of its own. A fabricated
        # HOLD is not a valid production signal.
        return None

    def calculate_confidence(self, signal=None):
        signal = str(signal or '').upper()
        if signal not in {'BUY', 'SELL'}:
            return None
        evidence = 0
        rsi = self.indicator_data.get('rsi')
        trend = str(self.indicator_data.get('trend') or '').lower()
        try:
            rsi = float(rsi) if rsi is not None else None
        except (TypeError, ValueError):
            rsi = None
        if rsi is not None and ((signal == 'BUY' and rsi < 30) or (signal == 'SELL' and rsi > 70)):
            evidence += 1
        if (signal == 'BUY' and trend in {'up', 'uptrend', 'bullish'}) or (signal == 'SELL' and trend in {'down', 'downtrend', 'bearish'}):
            evidence += 1
        if evidence == 0:
            return None
        # Deterministic confidence from observed strategy evidence, not a
        # placeholder/default percentage.
        return 40.0 if evidence == 1 else 80.0

    def calculate_stop_loss(self):
        return self._price_delta(-0.01)

    def calculate_take_profit(self):
        return self._price_delta(0.02)

    def calculate_position_size(self):
        parameters = getattr(self.configuration, 'parameters', {}) or {}
        return Decimal(str(parameters.get('stake', 1)))

    def evaluate_criteria(self, signal, confidence):
        criteria = getattr(self.configuration, 'criteria', {}) or {}
        passed, reasons = CriteriaEngine().evaluate(
            criteria,
            self.market_data,
            self.indicator_data,
            signal=signal,
            confidence=confidence,
        )
        self.criteria_result = {'passed': passed, 'reasons': reasons}
        return passed

    def execute(self):
        signal = self.generate_signal()
        confidence = self.calculate_confidence(signal)
        if signal not in SIGNAL_TYPES or signal is None:
            signal = None
            confidence = None

        if signal is not None and not self.evaluate_criteria(signal, confidence):
            signal = None
            confidence = None

        return {
            'signal': signal,
            'confidence': confidence,
            'criteria': self.criteria_result,
            'entry_price': self.market_data.get('price') or self.market_data.get('close'),
            'stop_loss': self.calculate_stop_loss(),
            'take_profit': self.calculate_take_profit(),
            'position_size': str(self.calculate_position_size()),
        }

    def shutdown(self):
        self.initialized = False
        return True

    def _price_delta(self, pct):
        price = self.market_data.get('price') or self.market_data.get('close')
        return None if price is None else Decimal(str(price)) * (Decimal('1') + Decimal(str(pct)))
