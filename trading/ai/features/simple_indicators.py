"""
Simple technical indicator implementations used by the dataset builder.
These are lightweight numpy-based implementations to avoid heavy deps.
"""
from typing import List, Dict
import numpy as np


def sma(values, period):
    vals = np.array(values)
    if len(vals) < period:
        return [None] * len(vals)
    out = np.convolve(vals, np.ones(period)/period, mode='valid')
    return [None]*(period-1) + out.tolist()


def returns(values):
    vals = np.array(values)
    ret = np.diff(vals) / vals[:-1]
    return [0.0] + ret.tolist()


def ema(values, period):
    vals = np.array(values)
    alpha = 2/(period+1)
    out = []
    prev = vals[0]
    for v in vals:
        prev = alpha * v + (1-alpha) * prev
        out.append(prev)
    return out


def compute_basic_features(candles: List[Dict]) -> List[Dict]:
    closes = [c['close'] for c in candles]
    highs = [c['high'] for c in candles]
    lows = [c['low'] for c in candles]

    sma5 = sma(closes, 5)
    sma20 = sma(closes, 20)
    ret = returns(closes)
    ema10 = ema(closes, 10)

    features = []
    for i in range(len(closes)):
        features.append({
            'close': closes[i],
            'sma5': sma5[i] if i < len(sma5) else None,
            'sma20': sma20[i] if i < len(sma20) else None,
            'ema10': ema10[i] if i < len(ema10) else None,
            'ret1': ret[i] if i < len(ret) else 0.0,
            'range': highs[i] - lows[i],
        })
    return features
