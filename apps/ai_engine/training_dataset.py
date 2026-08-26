from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from django.db.models import Q

from .data_pipeline import AIDataPipeline
from .models import PredictionOutcome
from trading.ai.candlestick_features import FEATURE_NAMES, feature_vector


@dataclass(frozen=True)
class FeatureDataset:
    X: np.ndarray
    y: np.ndarray
    metadata: dict[str, Any]


def _historical_ai_feedback(symbol: str, timeframe: str, before) -> tuple[float, float, int]:
    """Return only feedback resolved before the sample timestamp.

    This prevents the model from seeing future prediction outcomes during
    training. The returned values are rolling accuracy, mean return and count.
    """
    outcomes = PredictionOutcome.objects.filter(
        prediction__symbol=symbol,
        prediction__timeframe=timeframe,
        resolved_at__isnull=False,
        resolved_at__lte=before,
    ).filter(Q(correct=True) | Q(correct=False)).order_by("-resolved_at")[:100]
    rows = list(outcomes.values_list("correct", "actual_return"))
    if not rows:
        return 0.5, 0.0, 0
    accuracy = sum(bool(correct) for correct, _ in rows) / len(rows)
    mean_return = sum(float(ret or 0.0) for _, ret in rows) / len(rows)
    return float(accuracy), float(mean_return), len(rows)


def build_direction_dataset(symbol: str, timeframe: str = "M1", limit: int = 5000) -> FeatureDataset:
    """Build a chronological next-candle direction dataset with AI feedback.

    The three feedback features are calculated using only outcomes resolved at
    or before the current candle timestamp. Therefore historical AI performance
    can influence future samples without leaking future outcomes.
    """
    pipeline = AIDataPipeline()
    candles = pipeline.dataset(symbol, timeframe=timeframe, limit=limit)
    if len(candles) < 251:
        raise ValueError(f"Insufficient candles for {symbol}/{timeframe}: {len(candles)}; need at least 251")

    rows: list[list[float]] = []
    labels: list[int] = []
    feedback_rows = 0
    for i in range(60, len(candles) - 1):
        window = candles[i - 59 : i + 1]
        try:
            features = list(feature_vector(window))
            timestamp = candles[i].get("timestamp") or candles[i].get("time")
            accuracy, mean_return, count = _historical_ai_feedback(symbol, timeframe, timestamp)
            features.extend([accuracy, mean_return, float(count)])
            rows.append(features)
            labels.append(int(float(candles[i + 1]["close"]) > float(candles[i]["close"])))
            feedback_rows += int(count > 0)
        except (TypeError, ValueError, KeyError, FloatingPointError):
            continue

    if not rows:
        raise ValueError(f"No valid feature rows for {symbol}/{timeframe}")

    feedback_names = ["ai_feedback_accuracy", "ai_feedback_mean_return", "ai_feedback_sample_count"]
    return FeatureDataset(
        X=np.asarray(rows, dtype=np.float64),
        y=np.asarray(labels, dtype=np.int8),
        metadata={
            **pipeline.dataset_metadata(symbol, timeframe),
            "rows": len(rows),
            "feature_count": len(FEATURE_NAMES) + len(feedback_names),
            "feature_set": list(FEATURE_NAMES) + feedback_names,
            "label": "next_candle_direction",
            "window": 60,
            "leakage_safe": True,
            "feedback_rows": feedback_rows,
            "feedback_source": "PredictionOutcome",
        },
    )
