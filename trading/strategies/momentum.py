from .base import BaseStrategy


class MomentumStrategy(BaseStrategy):

    def generate_signal(self, prices):

        if len(prices) < 2:
            return None

        if prices[-1] > prices[-2]:
            return "BUY"

        if prices[-1] < prices[-2]:
            return "SELL"

        return None