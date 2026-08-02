import logging
from typing import List, Dict, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class MarketStructureDetector:
    """Detect basic market structure: swing highs/lows, HH/HL/LL/LH, breaks and simple order-block zones.

    This is a pragmatic, readable implementation intended for Phase 6 integration
    and can be iterated on later for precision and performance.
    """

    def __init__(self, lookback: int = 3):
        # lookback for local swing detection (candles to left/right)
        self.lookback = max(1, int(lookback))

    def _is_swing_high(self, highs: List[float], idx: int) -> bool:
        left = highs[max(0, idx - self.lookback):idx]
        right = highs[idx + 1: idx + 1 + self.lookback]
        return all(highs[idx] > x for x in left) and all(highs[idx] > x for x in right)

    def _is_swing_low(self, lows: List[float], idx: int) -> bool:
        left = lows[max(0, idx - self.lookback):idx]
        right = lows[idx + 1: idx + 1 + self.lookback]
        return all(lows[idx] < x for x in left) and all(lows[idx] < x for x in right)

    def detect_swings(self, highs: List[float], lows: List[float]) -> Dict[str, List[Tuple[int, float]]]:
        """Return swing highs and lows as lists of (index, price)."""
        swing_highs = []
        swing_lows = []

        for i in range(len(highs)):
            try:
                if self._is_swing_high(highs, i):
                    swing_highs.append((i, highs[i]))
                if self._is_swing_low(lows, i):
                    swing_lows.append((i, lows[i]))
            except Exception:
                continue

        return {"highs": swing_highs, "lows": swing_lows}

    def determine_structure(self, swings: Dict[str, List[Tuple[int, float]]]) -> str:
        """Return a simple structure label based on most recent swings: 'UPTREND','DOWNTREND','RANGE', 'UNKNOWN'."""
        highs = swings.get('highs', [])
        lows = swings.get('lows', [])

        if not highs or not lows:
            return 'UNKNOWN'

        # get last two swings of each type
        last_highs = highs[-2:]
        last_lows = lows[-2:]

        if len(last_highs) >= 2 and len(last_lows) >= 2:
            # indices increasing in time; compare prices
            h1 = last_highs[-2][1]
            h2 = last_highs[-1][1]
            l1 = last_lows[-2][1]
            l2 = last_lows[-1][1]

            # Higher Highs and Higher Lows => uptrend
            if h2 > h1 and l2 > l1:
                return 'UPTREND'
            # Lower Highs and Lower Lows => downtrend
            if h2 < h1 and l2 < l1:
                return 'DOWNTREND'

        # fallback: small variance => range
        all_prices = [p for _, p in highs + lows]
        if len(all_prices) >= 5 and (max(all_prices) - min(all_prices)) / (np.mean(all_prices) + 1e-9) < 0.02:
            return 'RANGE'

        return 'UNKNOWN'

    def detect_break_of_structure(self, closes: List[float], swings: Dict[str, List[Tuple[int, float]]]) -> Optional[Dict]:
        """Detect breaks of recent swing structure. Returns dict with info if detected.

        Improved logic:
        - Use last confirmed swing high/low (not just any swing) by picking the most recent swing
        - Require the break to be by a configurable buffer (slippage/false break tolerance)
        - Return which swing index was broken for retest checks
        """
        highs = swings.get('highs', [])
        lows = swings.get('lows', [])

        if not highs or not lows or len(closes) == 0:
            return None

        last_close = closes[-1]

        # choose most recent swing entries
        last_high_idx, last_high = highs[-1]
        last_low_idx, last_low = lows[-1]

        buffer = 1e-8
        # bullish break when close strictly above last swing high
        if last_close > last_high + buffer:
            return {'type': 'BOS_UP', 'level': last_high, 'price': last_close, 'swing_idx': last_high_idx}
        # bearish break when close strictly below last swing low
        if last_close < last_low - buffer:
            return {'type': 'BOS_DOWN', 'level': last_low, 'price': last_close, 'swing_idx': last_low_idx}

        return None

    def detect_change_of_character(self, closes: List[float], swings: Dict[str, List[Tuple[int, float]]], retest_window: int = 3) -> Optional[Dict]:
        """Change of character detection: detect BOS then look for retest within `retest_window` candles.

        Returns dict when COC detected: {'type': 'COC_UP'|'COC_DOWN', 'level': level, 'retest_idx': idx}
        """
        bos = self.detect_break_of_structure(closes, swings)
        if not bos:
            return None

        swing_idx = bos.get('swing_idx')
        level = bos.get('level')

        # scan last `retest_window` candles (excluding the break candle) for a retest touching the level
        # ensure we have enough closes
        if len(closes) < 2:
            return None

        start = max(0, len(closes) - retest_window - 1)
        # examine candles after the break (including break candle)
        for idx in range(start, len(closes)-1):
            c = closes[idx]
            # if price revisits the level (approx), consider as retest
            if abs(c - level) <= (abs(level) * 0.001 + 1e-8):
                # determine direction
                if bos['type'] == 'BOS_UP':
                    return {'type': 'COC_UP', 'level': level, 'retest_idx': idx}
                else:
                    return {'type': 'COC_DOWN', 'level': level, 'retest_idx': idx}

        return None

    def detect_order_blocks(self, opens: List[float], highs: List[float], lows: List[float], closes: List[float], multiplier: float = 1.5) -> List[Dict]:
        """Naive order block detection: find large-range candles as potential OB zones.

        Returns list of zones: {'type':'bull'|'bear','idx', 'high', 'low', 'range'}
        """
        ranges = [h - l for h, l in zip(highs, lows)]
        avg_range = float(np.mean(ranges)) if ranges else 0.0
        ob_zones = []

        for i, r in enumerate(ranges):
            if r > avg_range * multiplier:
                if closes[i] > opens[i]:
                    ob_type = 'bull'
                else:
                    ob_type = 'bear'

                ob_zones.append({
                    'type': ob_type,
                    'idx': i,
                    'high': highs[i],
                    'low': lows[i],
                    'range': float(r)
                })

        return ob_zones

    def detect_fair_value_gaps(self, opens: List[float], highs: List[float], lows: List[float], closes: List[float]) -> List[Dict]:
        """Detect fair value gaps (gaps in candle bodies with no overlap)."""
        gaps = []
        for i in range(1, len(opens)):
            prev_high = max(opens[i-1], closes[i-1])
            prev_low = min(opens[i-1], closes[i-1])
            curr_high = max(opens[i], closes[i])
            curr_low = min(opens[i], closes[i])

            # Bullish gap: current body sits above previous body
            if curr_low > prev_high:
                gaps.append({'type': 'bull', 'start_idx': i-1, 'end_idx': i, 'high': curr_high, 'low': curr_low})
            # Bearish gap: current body sits below previous body
            elif curr_high < prev_low:
                gaps.append({'type': 'bear', 'start_idx': i-1, 'end_idx': i, 'high': curr_high, 'low': curr_low})

        return gaps

    def detect_support_resistance_zones(self, highs: List[float], lows: List[float], tolerance_pct: float = 0.003) -> List[Dict]:
        """Detect support and resistance zones from swing highs and lows."""
        swings = self.detect_swings(highs, lows)
        zones = []

        for direction, points in [('resistance', swings['highs']), ('support', swings['lows'])]:
            grouped = []
            for idx, price in points:
                placed = False
                for zone in grouped:
                    if abs(price - zone['price']) <= abs(price) * tolerance_pct:
                        zone['count'] += 1
                        zone['indexes'].append(idx)
                        zone['price'] = (zone['price'] * (zone['count'] - 1) + price) / zone['count']
                        placed = True
                        break
                if not placed:
                    grouped.append({'type': direction, 'price': float(price), 'count': 1, 'indexes': [idx]})

            zones.extend(grouped)

        return sorted(zones, key=lambda z: z['price'], reverse=True)

    def detect_equal_price_levels(self, highs: List[float], lows: List[float], tolerance_pct: float = 0.002, repeat_threshold: int = 2) -> Dict[str, List[Dict]]:
        """Detect equal highs and equal lows that indicate liquidity clusters."""
        equal_levels = {'equal_highs': [], 'equal_lows': []}

        for key, prices in [('equal_highs', highs), ('equal_lows', lows)]:
            groups = []
            for price in prices:
                placed = False
                for group in groups:
                    if abs(price - group['price']) <= abs(price) * tolerance_pct:
                        group['count'] += 1
                        group['prices'].append(price)
                        group['price'] = float(np.mean(group['prices']))
                        placed = True
                        break
                if not placed:
                    groups.append({'price': float(price), 'count': 1, 'prices': [price]})

            equal_levels[key] = [
                {'price': group['price'], 'count': group['count']}
                for group in groups
                if group['count'] >= repeat_threshold
            ]

        return equal_levels

    def detect_liquidity_pools(self, highs: List[float], lows: List[float], repeat_threshold: int = 2, tolerance_pct: float = 0.002) -> List[Dict]:
        """Detect liquidity pools by repeated levels in recent highs or lows."""
        pools = []
        price_levels = []

        for level in highs + lows:
            matched = False
            for pool in price_levels:
                if abs(level - pool['price']) <= abs(level) * tolerance_pct:
                    pool['count'] += 1
                    pool['prices'].append(level)
                    pool['price'] = float(np.mean(pool['prices']))
                    matched = True
                    break
            if not matched:
                price_levels.append({'price': float(level), 'count': 1, 'prices': [level]})

        for pool in price_levels:
            if pool['count'] >= repeat_threshold:
                pools.append({'price': pool['price'], 'count': pool['count']})

        return sorted(pools, key=lambda p: p['count'], reverse=True)

    def multi_timeframe_alignment(self, structures: Dict[str, str]) -> str:
        """Return alignment state across multiple timeframes."""
        if not structures:
            return 'UNKNOWN'

        # Accept either mapping of timeframe->structure-string or timeframe->info-dict
        values = []
        for v in structures.values():
            if isinstance(v, dict):
                values.append(v.get('structure', 'UNKNOWN'))
            else:
                values.append(v)

        if all(v == 'UPTREND' for v in values):
            return 'BULLISH_ALIGNMENT'
        if all(v == 'DOWNTREND' for v in values):
            return 'BEARISH_ALIGNMENT'
        if any(v == 'RANGE' for v in values) and not any(v == 'UNKNOWN' for v in values):
            return 'RANGING_ALIGNMENT'
        return 'MIXED_ALIGNMENT'

    def structure_insight(self, highs: List[float], lows: List[float], opens: List[float], closes: List[float], multi_timeframes: Optional[Dict[str, Dict[str, str]]] = None) -> Dict:
        """Return full market structure insight summary."""
        swings = self.detect_swings(highs, lows)
        structure = self.determine_structure(swings)
        bos = self.detect_break_of_structure(closes, swings)
        coc = self.detect_change_of_character(closes, swings)
        ob_zones = self.detect_order_blocks(opens, highs, lows, closes)
        fvg = self.detect_fair_value_gaps(opens, highs, lows, closes)
        zones = self.detect_support_resistance_zones(highs, lows)
        liquidity = self.detect_liquidity_pools(highs, lows)

        equal_levels = self.detect_equal_price_levels(highs, lows)

        alignment = None
        if multi_timeframes:
            alignment = self.multi_timeframe_alignment({tf: info.get('structure', 'UNKNOWN') for tf, info in multi_timeframes.items()})

        return {
            'structure': structure,
            'swing_highs': swings['highs'],
            'swing_lows': swings['lows'],
            'break_of_structure': bos,
            'change_of_character': coc,
            'order_blocks': ob_zones,
            'fair_value_gaps': fvg,
            'support_resistance_zones': zones,
            'equal_highs': equal_levels['equal_highs'],
            'equal_lows': equal_levels['equal_lows'],
            'liquidity_pools': liquidity,
            'alignment': alignment,
        }


__all__ = ['MarketStructureDetector']
