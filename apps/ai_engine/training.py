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
from trading.ai.candlestick_features import FEATURE_NAMES

logger = logging.getLogger(__name__)
FEATURES = tuple(FEATURE_NAMES)
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
        path = Path(configured or (Path(__file__).resolve().parents[2] / "trading" / "ai" / "models"))
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


class MarketModelTrainer:
    """Train broker-independent directional models from canonical market data."""

    def train_symbol(self, symbol: str, timeframe: str = "M1", min_accuracy: float = 0.52) -> dict[str, Any]:
        timeframe = normalize_timeframe(timeframe)
        dataset = build_direction_dataset(symbol, timeframe)
        X, y = dataset.X, dataset.y
        split = int(len(X) * 0.8)
        X_train, X_test, y_train, y_test = X[:split], X[split:], y[:split], y[split:]
        if len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
            raise ValueError(f"Training data for {symbol}/{timeframe} does not contain both classes")

        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
        candidates: list[tuple[str, Any]] = [("rf", RandomForestClassifier(n_estimators=300, max_depth=10, min_samples_leaf=3, random_state=42, n_jobs=-1, class_weight="balanced"))]
        try:
            from xgboost import XGBClassifier
            candidates.append(("xgb", XGBClassifier(n_estimators=300, max_depth=5, learning_rate=0.05, subsample=0.9, colsample_bytree=0.9, eval_metric="logloss", random_state=42, n_jobs=2)))
        except Exception:
            logger.info("XGBoost unavailable; continuing with RF")
        try:
            from lightgbm import LGBMClassifier
            candidates.append(("lgb", LGBMClassifier(n_estimators=300, max_depth=7, learning_rate=0.05, subsample=0.9, colsample_bytree=0.9, random_state=42, verbosity=-1)))
        except Exception:
            logger.info("LightGBM unavailable; continuing with RF/XGB")

        results = []
        model_dir = _model_dir()
        for algorithm, model in candidates:
            model.fit(X_train, y_train)
            pred = model.predict(X_test)
            probability = model.predict_proba(X_test)[:, 1] if hasattr(model, "predict_proba") else pred
            accuracy = float(accuracy_score(y_test, pred))
            metrics = {
                "accuracy": accuracy,
                "precision": float(precision_score(y_test, pred, zero_division=0)),
                "recall": float(recall_score(y_test, pred, zero_division=0)),
                "f1": float(f1_score(y_test, pred, zero_division=0)),
                "auc": float(roc_auc_score(y_test, probability)) if len(np.unique(y_test)) > 1 else 0.5,
                "samples": int(len(X)),
                "train_samples": int(len(X_train)),
                "test_samples": int(len(X_test)),
                "feature_count": len(FEATURES),
                "feature_set": list(FEATURES),
            }
            results.append((algorithm, model, metrics))
        eligible = [item for item in results if item[2]["accuracy"] >= min_accuracy]
        if not eligible:
            raise ValueError(f"No model passed validation gate for {symbol}/{timeframe}; best accuracy={max(x[2]['accuracy'] for x in results):.4f}")

        with transaction.atomic():
            job = TrainingJob.objects.create(status="running", started_at=timezone.now())
            published = []
            for algorithm, model, metrics in eligible:
                path = model_dir / f"{symbol}_{timeframe}_{algorithm}.pkl"
                _atomic_dump(model, path)
                name = f"{symbol}-{timeframe}-{algorithm}"
                version = timezone.now().strftime("%Y%m%d%H%M%S")
                metadata = {"features": list(FEATURES), "artifact": str(path), "validation": metrics, "dataset": dataset.metadata, "knowledge_source": "canonical_market_data", "training_target": "next_candle_direction"}
                ai_model = AIModel.objects.create(name=name, version=version, algorithm=algorithm, framework="sklearn", status="active", accuracy=metrics["accuracy"], precision=metrics["precision"], recall=metrics["recall"], f1_score=metrics["f1"], auc=metrics["auc"], metadata=metadata)
                ModelVersion.objects.create(model=ai_model, version=version, training_dataset=f"market_data:{symbol}:{timeframe}", feature_set={"features": list(FEATURES), "provenance": dataset.metadata}, hyperparameters={"algorithm": algorithm})
                published.append({"algorithm": algorithm, "accuracy": metrics["accuracy"], "path": str(path), "features": len(FEATURES)})
            best = max(published, key=lambda item: item["accuracy"])
            AIModel.objects.filter(name__startswith=f"{symbol}-{timeframe}-", status="champion").update(status="active")
            champion = AIModel.objects.filter(name=f"{symbol}-{timeframe}-{best['algorithm']}", status="active").order_by("-created_at").first()
            if champion is None:
                raise RuntimeError("Champion model was not persisted")
            champion.status = "champion"
            champion.save(update_fields=["status"])
            job.model = champion
            job.status = "completed"
            job.completed_at = timezone.now()
            job.duration = (job.completed_at - job.started_at).total_seconds()
            job.metrics = {"symbol": symbol, "timeframe": timeframe, "published": published, "champion": best, "dataset": dataset.metadata}
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
