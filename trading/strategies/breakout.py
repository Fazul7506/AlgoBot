from .base import BaseStrategy


class BreakoutStrategy(BaseStrategy):

    def __init__(self, window=20):
        self.window = window

    def generate_signal(self, prices):

        if len(prices) < self.window + 1:
            return None

        recent = prices[-(self.window + 1):-1]
        current = prices[-1]

        if current > max(recent):
            return "BUY"

        if current < min(recent):
            return "SELL"

        return None
