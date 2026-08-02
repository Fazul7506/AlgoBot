from .base import BaseStrategy
import numpy as np


class ScalpingStrategy(BaseStrategy):

    def __init__(self, window=5, threshold=0.0015):
        self.window = window
        self.threshold = threshold

    def generate_signal(self, prices):
        if len(prices) < self.window + 1:
            return None

        recent = np.array(prices[-(self.window + 1):], dtype=float)
        returns = np.diff(recent) / (recent[:-1] + 1e-9)
        momentum = float(np.sum(returns))

        if momentum > self.threshold:
            return "BUY"

        if momentum < -self.threshold:
            return "SELL"

        return None
