from .base import BaseStrategy
import numpy as np


class RSIReversalStrategy(BaseStrategy):

    def __init__(self, period=14, overbought=70, oversold=30):
        self.period = period
        self.overbought = overbought
        self.oversold = oversold

    def _rsi(self, prices):
        if len(prices) < self.period + 1:
            return None

        deltas = np.diff(np.array(prices, dtype=float))
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)

        avg_gain = np.mean(gains[-self.period:])
        avg_loss = np.mean(losses[-self.period:])

        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0

        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def generate_signal(self, prices):
        if len(prices) < self.period + 1:
            return None

        rsi = self._rsi(prices[-(self.period + 1):])
        if rsi is None:
            return None

        if rsi > self.overbought:
            return "SELL"

        if rsi < self.oversold:
            return "BUY"

        return None
