from trading.services.signal_service import SignalService
from trading.services.market_regime import MarketRegimeDetector
from trading.strategies import registry


REGIME_STRATEGY_MAP = {
    'trending': 'trend',
    'ranging': 'mean_reversion',
    'volatile': 'breakout',
    'quiet': 'scalping',
}


class StrategyManager:

    def __init__(self, default='trend', config=None, auto_regime=True):
        self.auto_regime = auto_regime
        self.config = config or {}
        self.strategy_name = default
        self.strategy = self._build_strategy(default)

    def _build_strategy(self, strategy_name):
        cls = registry.get(strategy_name)
        if not cls:
            cls = registry.get('momentum')
            self.strategy_name = 'momentum'

        try:
            return cls(**(self.config or {}))
        except Exception:
            return cls()

    def set_strategy(self, strategy_name, config=None):
        self.strategy_name = strategy_name
        self.config = config or {}
        self.strategy = self._build_strategy(strategy_name)

    def available_strategies(self):
        return registry.available()

    def process_tick(self, symbol, prices):
        regime = MarketRegimeDetector.detect(prices)
        chosen = REGIME_STRATEGY_MAP.get(regime, self.strategy_name)

        if self.auto_regime and chosen != self.strategy_name:
            self.set_strategy(chosen)

        signal = self.strategy.generate_signal(prices)

        if signal:
            SignalService.create_signal(
                symbol=symbol,
                strategy=self.strategy_name,
                direction=signal,
                confidence=55,
                market_regime=regime,
            )

            print(f"SIGNAL: {signal} from {self.strategy_name} (regime={regime})")

            return {
                'signal': signal,
                'strategy': self.strategy_name,
                'confidence': 55,
                'market_regime': regime,
            }

        return None
