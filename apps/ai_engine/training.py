from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import AIModel, ModelVersion, TrainingJob
from .training_dataset import build_direction_dataset
from .validation import walk_forward_validate
from .candlestick_features import FEATURE_NAMES

logger = logging.getLogger(__name__)
FEATURES = tuple(FEATURE_NAMES) + ("ai_feedback_accuracy", "ai_feedback_mean_return", "ai_feedback_sample_count")
TIMEFRAME_ALIASES = {"M1": "1m", "M2": "2m", "M5": "5m", "M10": "10m", "M15": "15m", "M30": "30m", "H1": "1h", "H4": "4h", "D1": "1d"}


def normalize_timeframe(timeframe: str) -> str:
    value = str(timeframe or "M1").strip()
    canonical = TIMEFRAME_ALIASES.get(value.upper(), value.lower())
    if canonical not in {"1s", "5s", "15s", "30s", "1m", "2m", "5m", "10m", "15m", "30m", "1h", "4h", "1d"}:
        raise ValueError(f"Unsupported candle timeframe: {timeframe}")
    return canonical


def _model_dir() -> Path:
    configured = os.environ.get("AI_MODEL_DIR", "").strip()
    if getattr(settings, "DEBUG", False):
        path = Path(configured or (Path(__file__).resolve().parent / "models"))
    else:
        if not configured:
            raise RuntimeError("AI_MODEL_DIR must point to durable model storage in production")
        path = Path(configured)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_dump(model: Any, path: Path) -> None:
    import joblib
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
        tmp = Path(handle.name)
    try:
        joblib.dump(model, tmp)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _candidate_factories():
    from sklearn.ensemble import RandomForestClassifier
    candidates = [("rf", lambda: RandomForestClassifier(n_estimators=300, max_depth=10, min_samples_leaf=3, random_state=42, n_jobs=-1, class_weight="balanced"))]
    try:
        from xgboost import XGBClassifier
        candidates.append(("xgb", lambda: XGBClassifier(n_estimators=300, max_depth=5, learning_rate=0.05, subsample=0.9, colsample_bytree=0.9, eval_metric="logloss", random_state=42, n_jobs=2)))
    except Exception:
        logger.info("XGBoost unavailable; continuing with RF")
    try:
        from lightgbm import LGBMClassifier
        candidates.append(("lgb", lambda: LGBMClassifier(n_estimators=300, max_depth=7, learning_rate=0.05, subsample=0.9, colsample_bytree=0.9, random_state=42, verbosity=-1)))
    except Exception:
        logger.info("LightGBM unavailable; continuing with RF/XGB")
    return candidates


class MarketModelTrainer:
    """Train, walk-forward validate, and promote broker-independent models."""

    def train_symbol(self, symbol: str, timeframe: str = "M1", min_accuracy: float = 0.52) -> dict[str, Any]:
        timeframe = normalize_timeframe(timeframe)
        dataset = build_direction_dataset(symbol, timeframe)
        X, y, returns = dataset.X, dataset.y, dataset.next_returns
        if len(X) < 200 or len(np.unique(y)) < 2:
            raise ValueError(f"Training data for {symbol}/{timeframe} is insufficient for validation")

        candidates = _candidate_factories()
        results = []
        for algorithm, factory in candidates:
            validation = walk_forward_validate(factory, X, y, returns, folds=5)
            aggregate = validation["aggregate"]
            if aggregate["accuracy"] < min_accuracy:
                logger.info("Candidate failed accuracy gate", extra={"symbol": symbol, "algorithm": algorithm, "accuracy": aggregate["accuracy"]})
                continue
            score = (aggregate["accuracy"] * 0.30) + (aggregate["f1"] * 0.15) + (aggregate["sharpe"] * 0.20) + (aggregate["expectancy"] * 1000.0 * 0.20) + (min(aggregate["profit_factor"], 5.0) / 5.0 * 0.15)
            results.append((algorithm, factory, validation, float(score)))

        if not results:
            raise ValueError(f"No model passed walk-forward validation for {symbol}/{timeframe}")

        best_algorithm, best_factory, best_validation, best_score = max(results, key=lambda item: item[3])
        if best_validation["aggregate"]["expectancy"] <= 0 and best_validation["aggregate"]["total_return"] <= 0:
            raise ValueError(f"No profitable candidate passed validation for {symbol}/{timeframe}")

        model_dir = _model_dir()
        with transaction.atomic():
            job = TrainingJob.objects.create(status="running", started_at=timezone.now())
            model = best_factory()
            model.fit(X, y)
            path = model_dir / f"{symbol}_{timeframe}_{best_algorithm}.pkl"
            _atomic_dump(model, path)
            aggregate = best_validation["aggregate"]
            version = timezone.now().strftime("%Y%m%d%H%M%S")
            metrics = {
                "accuracy": aggregate["accuracy"], "precision": aggregate["precision"], "recall": aggregate["recall"],
                "f1": aggregate["f1"], "auc": aggregate["auc"], "expectancy": aggregate["expectancy"],
                "win_rate": aggregate["win_rate"], "profit_factor": aggregate["profit_factor"], "max_drawdown": aggregate["max_drawdown"],
                "sharpe": aggregate["sharpe"], "sortino": aggregate["sortino"], "total_return": aggregate["total_return"],
                "samples": int(len(X)), "feature_count": len(FEATURES), "feature_set": list(FEATURES),
                "walk_forward_folds": best_validation["folds"], "promotion_score": best_score,
            }
            name = f"{symbol}-{timeframe}-{best_algorithm}"
            metadata = {"features": list(FEATURES), "artifact": str(path), "validation": metrics, "dataset": dataset.metadata, "knowledge_source": "canonical_market_data_and_prediction_outcomes", "training_target": "next_candle_direction", "selection": "walk_forward_champion_challenger"}
            ai_model = AIModel.objects.create(name=name, version=version, algorithm=best_algorithm, framework="sklearn", status="experimental", accuracy=metrics["accuracy"], precision=metrics["precision"], recall=metrics["recall"], f1_score=metrics["f1"], auc=metrics["auc"], metadata=metadata)
            ModelVersion.objects.create(model=ai_model, version=version, training_dataset=f"market_data:{symbol}:{timeframe}", feature_set={"features": list(FEATURES), "provenance": dataset.metadata}, hyperparameters={"algorithm": best_algorithm, "selection_score": best_score})

            previous = AIModel.objects.filter(name=name, status="champion").exclude(pk=ai_model.pk).order_by("-created_at").first()
            promoted = previous is None or best_score > float((previous.metadata or {}).get("validation", {}).get("promotion_score", float("-inf")))
            if promoted:
                AIModel.objects.filter(name__startswith=f"{symbol}-{timeframe}-", status="champion").update(status="active")
                ai_model.status = "champion"
                ai_model.save(update_fields=["status"])
            else:
                ai_model.status = "active"
                ai_model.save(update_fields=["status"])

            job.model = ai_model
            job.status = "completed"
            job.completed_at = timezone.now()
            job.duration = (job.completed_at - job.started_at).total_seconds()
            job.metrics = {"symbol": symbol, "timeframe": timeframe, "algorithm": best_algorithm, "promoted": promoted, **metrics, "dataset": dataset.metadata}
            job.save(update_fields=["model", "status", "completed_at", "duration", "metrics"])
        return job.metrics

    def train_active_symbols(self, timeframe: str = "M1", min_accuracy: float = 0.52) -> dict[str, Any]:
        from apps.market_data.models import MarketSymbol
        timeframe = normalize_timeframe(timeframe)
        results = {}
        for symbol in MarketSymbol.objects.filter(is_active=True, is_tradable=True).values_list("symbol", flat=True):
            try:
                results[symbol] = self.train_symbol(symbol, timeframe, min_accuracy)
            except Exception as exc:
                logger.warning("AI training skipped", extra={"symbol": symbol, "timeframe": timeframe, "error": str(exc)})
                results[symbol] = {"status": "skipped", "error": str(exc)}
        return results
