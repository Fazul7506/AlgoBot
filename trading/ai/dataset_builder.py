"""
Dataset builder for Phase 9 AI pipeline.
- Extracts ticks/candles and builds feature matrix and labels.
- Lightweight, dependency-tolerant implementation.
"""
from typing import List, Dict, Tuple
from datetime import timedelta
from django.utils import timezone
import numpy as np

from trading.models.core import Tick, Candle, Trade


def sample_candles(symbol: str, timeframe: str, window: int = 100):
    """Return the last `window` candles for symbol/timeframe as list of dicts."""
    qs = Candle.objects.filter(symbol=symbol, timeframe=timeframe).order_by('-timestamp')[:window]
    # reverse to chronological
    return [
        {
            'timestamp': c.timestamp,
            'open': c.open,
            'high': c.high,
            'low': c.low,
            'close': c.close,
            'volume': c.volume,
        }
        for c in reversed(qs)
    ]


def build_label_for_candles(candles: List[Dict], horizon: int = 1, label_type: str = 'direction'):
    """Create labels for each candle based on future price movement.

    label_type: 'direction' -> UP/DOWN, 'return' -> future return
    horizon: number of candles ahead
    """
    closes = np.array([c['close'] for c in candles])
    labels = []
    for i in range(len(closes)):
        j = i + horizon
        if j >= len(closes):
            labels.append(None)
            continue
        future = closes[j]
        cur = closes[i]
        if label_type == 'direction':
            labels.append(1 if future > cur else 0)
        elif label_type == 'return':
            labels.append((future - cur) / cur)
        else:
            labels.append(None)
    return labels


def build_dataset(symbol: str, timeframe: str = 'M1', window: int = 200, horizon: int = 1):
    """Return X (features) and y (labels) for model training.

    Currently uses simple features: returns and rolling means — extend via `features/`.
    """
    candles = sample_candles(symbol, timeframe, window + horizon)
    if len(candles) < window:
        return None, None

    from trading.ai.features.simple_indicators import compute_basic_features

    features = compute_basic_features(candles)
    labels = build_label_for_candles(candles, horizon=horizon, label_type='direction')

    # drop last horizon rows with None label
    X = []
    y = []
    for feat, lab in zip(features, labels):
        if lab is None:
            continue
        X.append([feat[k] for k in sorted(feat.keys())])
        y.append(lab)

    return np.array(X), np.array(y)
