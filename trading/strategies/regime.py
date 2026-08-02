import numpy as np


class RegimeDetector:
    """Simple market regime detector for Phase 1.

    Rules:
    - If short>mid>long -> trending_up
    - If short<mid<long -> trending_down
    - If volatility (return std) > threshold -> volatile
    - Else -> ranging
    """

    @staticmethod
    def detect(prices, short=3, mid=10, long=20, vol_window=20, vol_thresh=0.005):
        if len(prices) < 2:
            return 'unknown'

        arr = np.array(prices)

        if len(arr) >= long:
            short_ma = arr[-short:].mean()
            mid_ma = arr[-mid:].mean()
            long_ma = arr[-long:].mean()

            if short_ma > mid_ma > long_ma:
                return 'trending_up'

            if short_ma < mid_ma < long_ma:
                return 'trending_down'

        # volatility: use log returns std
        if len(arr) >= vol_window:
            window = arr[-vol_window:]
            ret = np.diff(np.log(window + 1e-9))
            vol = ret.std()
            if vol > vol_thresh:
                return 'volatile'

        return 'ranging'
