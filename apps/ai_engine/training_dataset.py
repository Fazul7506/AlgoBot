from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from typing import Any

import numpy as np
from django.db.models import Q

from .data_pipeline import AIDataPipeline
from .models import PredictionOutcome
from .candlestick_features import FEATURE_NAMES, feature_vector

AI_FEEDBACK_FEATURE_NAMES = ("ai_feedback_accuracy", "ai_feedback_mean_return", "ai_feedback_sample_count")
STRATEGY_FEATURE_NAMES = ("strategy_signal_bias", "strategy_signal_confidence", "strategy_signal_count")
MODEL_FEATURE_NAMES = tuple(FEATURE_NAMES) + AI_FEEDBACK_FEATURE_NAMES + STRATEGY_FEATURE_NAMES


@dataclass(frozen=True)
class FeatureDataset:
    X: np.ndarray
    y: np.ndarray
    next_returns: np.ndarray
    metadata: dict[str, Any]


def _historical_ai_feedback(symbol: str, timeframe: str, before_epoch: int) -> tuple[float, float, int]:
    before = datetime.fromtimestamp(int(before_epoch), tz=dt_timezone.utc)
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


def current_ai_feedback(symbol: str, timeframe: str, before_epoch: int | None = None) -> tuple[float, float, int]:
    """Return only feedback that was resolved before the current market observation."""
    cutoff = datetime.now(tz=dt_timezone.utc) if before_epoch is None else datetime.fromtimestamp(int(before_epoch), tz=dt_timezone.utc)
    outcomes = PredictionOutcome.objects.filter(
        prediction__symbol=symbol,
        prediction__timeframe=timeframe,
        resolved_at__isnull=False,
        resolved_at__lte=cutoff,
    ).filter(Q(correct=True) | Q(correct=False)).order_by("-resolved_at")[:100]
    rows = list(outcomes.values_list("correct", "actual_return"))
    if not rows:
        return 0.5, 0.0, 0
    accuracy = sum(bool(correct) for correct, _ in rows) / len(rows)
    mean_return = sum(float(ret or 0.0) for _, ret in rows) / len(rows)
    return float(accuracy), float(mean_return), len(rows)


def current_strategy_signal_features(symbol: str, timeframe: str, before_epoch: int | None = None) -> tuple[float, float, int]:
    """Aggregate recent persisted strategy signals without leaking future timestamps."""
    from apps.strategies.models import StrategySignal

    cutoff = datetime.now(tz=dt_timezone.utc) if before_epoch is None else datetime.fromtimestamp(int(before_epoch), tz=dt_timezone.utc)
    signals = StrategySignal.objects.filter(
        symbol=symbol,
        timestamp__lte=cutoff,
        configuration__timeframe__in=(timeframe, timeframe.upper()),
    ).order_by("-timestamp")[:100]
    rows = list(signals.values_list("signal", "confidence"))
    if not rows:
        return 0.0, 0.0, 0
    def bias(signal):
        value = str(signal or "").upper()
        return 1.0 if value in {"BUY", "LONG", "UP", "CALL"} else -1.0 if value in {"SELL", "SHORT", "DOWN", "PUT"} else 0.0
    return (
        float(sum(bias(signal) for signal, _ in rows) / len(rows)),
        float(sum(float(confidence or 0.0) for _, confidence in rows) / len(rows) / 100.0),
        len(rows),
    )


def build_direction_dataset(symbol: str, timeframe: str = "M1", limit: int = 5000) -> FeatureDataset:
    pipeline = AIDataPipeline()
    candles = pipeline.dataset(symbol, timeframe=timeframe, limit=limit)
    if len(candles) < 251:
        raise ValueError(f"Insufficient candles for {symbol}/{timeframe}: {len(candles)}; need at least 251")

    rows: list[list[float]] = []
    labels: list[int] = []
    next_returns: list[float] = []
    feedback_rows = 0
    for i in range(60, len(candles) - 1):
        window = candles[i - 59 : i + 1]
        try:
            features = list(feature_vector(window))
            accuracy, mean_return, count = _historical_ai_feedback(symbol, timeframe, int(candles[i]["epoch"]))
            signal_bias, signal_confidence, signal_count = current_strategy_signal_features(symbol, timeframe, int(candles[i]["epoch"]))
            features.extend([accuracy, mean_return, float(count), signal_bias, signal_confidence, float(signal_count)])
            current_close = float(candles[i]["close"])
            next_close = float(candles[i + 1]["close"])
            if current_close == 0:
                continue
            rows.append(features)
            labels.append(int(next_close > current_close))
            next_returns.append((next_close - current_close) / current_close)
            feedback_rows += int(count > 0)
        except (TypeError, ValueError, KeyError, FloatingPointError, OverflowError):
            continue

    if not rows:
        raise ValueError(f"No valid feature rows for {symbol}/{timeframe}")

    feedback_names = list(AI_FEEDBACK_FEATURE_NAMES) + list(STRATEGY_FEATURE_NAMES)
    return FeatureDataset(
        X=np.asarray(rows, dtype=np.float64),
        y=np.asarray(labels, dtype=np.int8),
        next_returns=np.asarray(next_returns, dtype=np.float64),
        metadata={
            **pipeline.dataset_metadata(symbol, timeframe),
            "rows": len(rows),
            "feature_count": len(FEATURE_NAMES) + len(feedback_names),
            "feature_set": list(FEATURE_NAMES) + feedback_names,
            "label": "next_candle_direction",
            "return_target": "next_candle_close_return",
            "window": 60,
            "leakage_safe": True,
            "feedback_rows": feedback_rows,
            "feedback_source": "PredictionOutcome",
        },
    )
