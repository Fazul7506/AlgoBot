from .base import BaseStrategy
import numpy as np


class MeanReversionStrategy(BaseStrategy):

    def __init__(self, window=20, z_thresh=1.5):
        self.window = window
        self.z = z_thresh

    def generate_signal(self, prices):

        if len(prices) < self.window:
            return None

        window = np.array(prices[-self.window:])
        mean = window.mean()
        std = window.std() + 1e-9
        current = prices[-1]

        zscore = (current - mean) / std

        # If price is far above mean -> SELL (revert)
        if zscore > self.z:
            return "SELL"

        # If price is far below mean -> BUY (revert)
        if zscore < -self.z:
            return "BUY"

        return None
