import numpy as np
from typing import List, Dict, Optional


class MarketRegimeDetector:
    """Detect core market regimes from price data.

    Supports:
    - trending
    - ranging
    - volatile
    - quiet

    This detector is designed to support strategy switching and regime dashboards.
    """

    @staticmethod
    def detect_details(
        closes: List[float],
        opens: Optional[List[float]] = None,
        highs: Optional[List[float]] = None,
        lows: Optional[List[float]] = None,
        quiet_vol: float = 0.005,
        volatile_vol: float = 0.02,
        trend_pct_threshold: float = 0.015,
        quiet_range_pct: float = 0.008,
        window: int = 50,
    ) -> Dict[str, Optional[float]]:
        if not closes or len(closes) < 10:
            return {
                'regime': 'unknown',
                'trend_direction': 'neutral',
                'volatility': None,
                'range_pct': None,
                'trend_pct': None,
                'short_ma': None,
                'mid_ma': None,
                'long_ma': None,
            }

        arr = np.array(closes, dtype=float)
        lookback = min(len(arr), window)
        window_arr = arr[-lookback:]

        # Use log returns to characterize volatility.
        returns = np.diff(np.log(window_arr + 1e-9))
        volatility = float(np.std(returns)) if len(returns) > 0 else 0.0

        short_period = min(5, len(window_arr))
        mid_period = min(15, len(window_arr))
        long_period = min(35, len(window_arr))

        short_ma = float(np.mean(window_arr[-short_period:]))
        mid_ma = float(np.mean(window_arr[-mid_period:]))
        long_ma = float(np.mean(window_arr[-long_period:]))

        trend_delta = window_arr[-1] - window_arr[0]
        trend_pct = abs(trend_delta) / max(float(np.mean(window_arr)), 1e-9)
        range_pct = (float(np.max(window_arr)) - float(np.min(window_arr))) / max(float(np.mean(window_arr)), 1e-9)

        trend_direction = 'neutral'
        if window_arr[-1] > window_arr[0]:
            trend_direction = 'up'
        elif window_arr[-1] < window_arr[0]:
            trend_direction = 'down'

        if volatility < quiet_vol and range_pct < quiet_range_pct:
            regime = 'quiet'
        elif volatility > volatile_vol:
            regime = 'volatile'
        elif (short_ma > mid_ma > long_ma or short_ma < mid_ma < long_ma) and trend_pct > trend_pct_threshold:
            regime = 'trending'
        else:
            regime = 'ranging'

        return {
            'regime': regime,
            'trend_direction': trend_direction,
            'volatility': float(volatility),
            'range_pct': float(range_pct),
            'trend_pct': float(trend_pct),
            'short_ma': float(short_ma),
            'mid_ma': float(mid_ma),
            'long_ma': float(long_ma),
        }

    @staticmethod
    def detect(
        closes: List[float],
        opens: Optional[List[float]] = None,
        highs: Optional[List[float]] = None,
        lows: Optional[List[float]] = None,
        **kwargs,
    ) -> str:
        return MarketRegimeDetector.detect_details(closes, opens=opens, highs=highs, lows=lows, **kwargs).get('regime', 'unknown')


__all__ = ['MarketRegimeDetector']
