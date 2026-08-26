from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .data_pipeline import AIDataPipeline
from trading.ai.candlestick_features import FEATURE_NAMES, feature_vector


@dataclass(frozen=True)
class FeatureDataset:
    X: np.ndarray
    y: np.ndarray
    metadata: dict[str, Any]


def build_direction_dataset(symbol: str, timeframe: str = "M1", limit: int = 5000) -> FeatureDataset:
    """Build a chronological next-candle direction dataset with provenance.

    Features are calculated only from candles available before the target candle,
    preventing future leakage. Labels are the direction of the immediately next
    close relative to the current close.
    """
    pipeline = AIDataPipeline()
    candles = pipeline.dataset(symbol, timeframe=timeframe, limit=limit)
    if len(candles) < 251:
        raise ValueError(f"Insufficient candles for {symbol}/{timeframe}: {len(candles)}; need at least 251")

    rows: list[list[float]] = []
    labels: list[int] = []
    for i in range(60, len(candles) - 1):
        window = candles[i - 59 : i + 1]
        try:
            rows.append(feature_vector(window))
            labels.append(int(float(candles[i + 1]["close"]) > float(candles[i]["close"])))
        except (TypeError, ValueError, KeyError, FloatingPointError):
            continue

    if not rows:
        raise ValueError(f"No valid feature rows for {symbol}/{timeframe}")

    return FeatureDataset(
        X=np.asarray(rows, dtype=np.float64),
        y=np.asarray(labels, dtype=np.int8),
        metadata={
            **pipeline.dataset_metadata(symbol, timeframe),
            "rows": len(rows),
            "feature_count": len(FEATURE_NAMES),
            "feature_set": list(FEATURE_NAMES),
            "label": "next_candle_direction",
            "window": 60,
            "leakage_safe": True,
        },
    )
