from .base import BaseStrategy
import numpy as np


class EMACrossStrategy(BaseStrategy):

    def __init__(self, fast_span=8, slow_span=21):
        self.fast_span = fast_span
        self.slow_span = slow_span

    def _ema(self, prices, span):
        if len(prices) < span:
            return None

        weights = np.exp(np.linspace(-1., 0., span))
        ema = np.convolve(prices, weights / weights.sum(), mode='valid')
        return float(ema[-1])

    def generate_signal(self, prices):
        if len(prices) < self.slow_span:
            return None

        close = np.array(prices)
        fast = self._ema(close, self.fast_span)
        slow = self._ema(close, self.slow_span)

        if fast is None or slow is None:
            return None

        if fast > slow:
            return "BUY"

        if fast < slow:
            return "SELL"

        return None
