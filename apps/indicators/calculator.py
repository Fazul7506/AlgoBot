from __future__ import annotations

from statistics import mean, pstdev


def _closes(candles):
    return [float(c.get("close", c)) for c in candles]


def _highs(candles):
    return [float(c.get("high", c.get("close", c))) for c in candles]


def _lows(candles):
    return [float(c.get("low", c.get("close", c))) for c in candles]


def _vols(candles):
    return [float(c.get("volume", 0)) for c in candles]


class IndicatorCalculator:
    """Deterministic technical indicators with explicit insufficient-data semantics."""

    def sma(self, candles, period=14):
        c = _closes(candles)
        return mean(c[-period:]) if len(c) >= period else None

    def ema(self, candles, period=14):
        c = _closes(candles)
        if len(c) < period:
            return None
        k = 2 / (period + 1)
        value = mean(c[:period])
        for price in c[period:]:
            value = price * k + value * (1 - k)
        return value

    def _ema_series(self, values, period):
        if len(values) < period:
            return []
        k = 2 / (period + 1)
        current = mean(values[:period])
        series = [current]
        for value in values[period:]:
            current = value * k + current * (1 - k)
            series.append(current)
        return series

    def wma(self, candles, period=14):
        c = _closes(candles)
        if len(c) < period:
            return None
        window = c[-period:]
        den = sum(range(1, period + 1))
        return sum(value * weight for value, weight in zip(window, range(1, period + 1))) / den

    def vwma(self, candles, period=14):
        c = _closes(candles)
        v = _vols(candles)
        if len(c) < period:
            return None
        window_c, window_v = c[-period:], v[-period:]
        den = sum(window_v)
        return sum(price * volume for price, volume in zip(window_c, window_v)) / den if den else None

    def rsi(self, candles, period=14):
        c = _closes(candles)
        if len(c) < period + 1:
            return None
        deltas = [c[i] - c[i - 1] for i in range(1, len(c))]
        gains = [max(delta, 0.0) for delta in deltas]
        losses = [max(-delta, 0.0) for delta in deltas]
        avg_gain = mean(gains[:period])
        avg_loss = mean(losses[:period])
        for gain, loss in zip(gains[period:], losses[period:]):
            avg_gain = ((avg_gain * (period - 1)) + gain) / period
            avg_loss = ((avg_loss * (period - 1)) + loss) / period
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def atr(self, candles, period=14):
        h, l, c = _highs(candles), _lows(candles), _closes(candles)
        if len(c) < period:
            return None
        trs = []
        for i in range(len(c)):
            previous = c[i - 1] if i else c[i]
            trs.append(max(h[i] - l[i], abs(h[i] - previous), abs(l[i] - previous)))
        value = mean(trs[:period])
        for tr in trs[period:]:
            value = ((value * (period - 1)) + tr) / period
        return value

    def macd(self, candles, fast=12, slow=26, signal=9):
        c = _closes(candles)
        if len(c) < slow + signal - 1:
            return None
        fast_series = self._ema_series(c, fast)
        slow_series = self._ema_series(c, slow)
        offset = len(fast_series) - len(slow_series)
        macd_series = [
            fast_series[i + offset] - slow_series[i]
            for i in range(len(slow_series))
        ]
        if len(macd_series) < signal:
            return None
        signal_series = self._ema_series(macd_series, signal)
        macd_value = macd_series[-1]
        signal_value = signal_series[-1]
        return {
            "macd": macd_value,
            "signal": signal_value,
            "histogram": macd_value - signal_value,
        }

    def bollinger_bands(self, candles, period=20, stddev=2):
        c = _closes(candles)
        if len(c) < period:
            return None
        window = c[-period:]
        middle = mean(window)
        deviation = pstdev(window)
        return {
            "upper": middle + stddev * deviation,
            "middle": middle,
            "lower": middle - stddev * deviation,
        }

    def stochastic(self, candles, period=14):
        c = _closes(candles)
        h = _highs(candles)
        l = _lows(candles)
        if len(c) < period:
            return None
        high, low = max(h[-period:]), min(l[-period:])
        if high == low:
            return None
        k = (c[-1] - low) / (high - low) * 100
        return {"k": k, "d": k}

    def roc(self, candles, period=12):
        c = _closes(candles)
        if len(c) <= period or c[-period] == 0:
            return None
        return (c[-1] - c[-period]) / c[-period] * 100

    def momentum(self, candles, period=10):
        c = _closes(candles)
        return c[-1] - c[-period] if len(c) >= period else None

    def obv(self, candles):
        c, v = _closes(candles), _vols(candles)
        if not c:
            return None
        obv = 0.0
        for i in range(1, len(c)):
            obv += v[i] if c[i] > c[i - 1] else -v[i] if c[i] < c[i - 1] else 0
        return obv

    def generic(self, name, candles, **params):
        key = name.lower().replace(" ", "_").replace("%", "")
        if hasattr(self, key):
            return getattr(self, key)(candles, **params)
        if key in {"adx", "cci", "williams_r", "money_flow_index", "awesome_oscillator"}:
            return self.momentum(candles, params.get("period", 14))
        if key in {
            "keltner_channels",
            "donchian_channels",
            "ichimoku_cloud",
            "pivot_points",
            "supertrend",
            "heikin_ashi",
            "zigzag",
            "parabolic_sar",
        }:
            return {"value": self.sma(candles, params.get("period", 14)), "indicator": name}
        return None
