"""
Feature store: caches computed features for symbols/timeframes to avoid recompute.
Simple in-memory cache; can be extended to Redis or DB-backed store.
"""
from typing import Dict, Any, Tuple
from functools import lru_cache

from trading.ai.dataset_builder import sample_candles
from trading.ai.features.simple_indicators import compute_basic_features


class FeatureStore:
    def __init__(self):
        self._cache = {}

    def get_features(self, symbol: str, timeframe: str = 'M1', window: int = 200):
        key = (symbol, timeframe, window)
        if key in self._cache:
            return self._cache[key]

        candles = sample_candles(symbol, timeframe, window)
        feats = compute_basic_features(candles)
        self._cache[key] = feats
        return feats

    def invalidate(self, symbol: str = None, timeframe: str = None):
        if symbol is None and timeframe is None:
            self._cache.clear()
            return
        keys = [k for k in self._cache.keys() if (symbol is None or k[0]==symbol) and (timeframe is None or k[1]==timeframe)]
        for k in keys:
            del self._cache[k]
