from .base import BaseStrategy
import numpy as np


class TrendStrategy(BaseStrategy):

    def __init__(self, short_window=3, mid_window=10, long_window=20):
        self.short = short_window
        self.mid = mid_window
        self.long = long_window

    def generate_signal(self, prices):

        if len(prices) < self.long:
            return None

        short_ma = np.mean(prices[-self.short:])
        mid_ma = np.mean(prices[-self.mid:])
        long_ma = np.mean(prices[-self.long:])

        # Trend alignment
        if short_ma > mid_ma > long_ma:
            return "BUY"

        if short_ma < mid_ma < long_ma:
            return "SELL"

        return None
