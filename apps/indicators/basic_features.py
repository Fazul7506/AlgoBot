"""Lightweight numeric features shared by live strategy execution and training."""
from __future__ import annotations
from typing import Dict, List
import numpy as np


def sma(values, period):
    vals = np.asarray(values, dtype=float)
    if len(vals) < period:
        return [None] * len(vals)
    out = np.convolve(vals, np.ones(period) / period, mode="valid")
    return [None] * (period - 1) + out.tolist()


def returns(values):
    vals = np.asarray(values, dtype=float)
    if len(vals) < 2:
        return [0.0] * len(vals)
    ret = np.diff(vals) / np.where(vals[:-1] == 0, 1.0, vals[:-1])
    return [0.0] + ret.tolist()


def ema(values, period):
    vals = np.asarray(values, dtype=float)
    if not len(vals):
        return []
    alpha = 2 / (period + 1)
    out = []
    prev = vals[0]
    for value in vals:
        prev = alpha * value + (1 - alpha) * prev
        out.append(prev)
    return out


def compute_basic_features(candles: List[Dict]) -> List[Dict]:
    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    sma5, sma20, ret, ema10 = sma(closes, 5), sma(closes, 20), returns(closes), ema(closes, 10)
    return [{"close": closes[i], "sma5": sma5[i], "sma20": sma20[i], "ema10": ema10[i], "ret1": ret[i], "range": highs[i] - lows[i]} for i in range(len(closes))]
