"""Production ensemble inference for broker-independent trading models.

All registered model artifacts receive the same feature vector.  The ensemble
aggregates calibrated directional probabilities, uses validation metrics for
optional weights, and exposes BUY/SELL/AVOID without changing the legacy
UP/DOWN + probability contract consumed by the existing AI engine.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import numpy as np

MODEL_DIR = os.environ.get("AI_MODEL_DIR", os.path.join(os.path.dirname(__file__), "models"))
MODEL_TYPES = ("rf", "xgb", "lgb", "lstm")
DEFAULT_WEIGHTS = {"rf": 1.0, "xgb": 1.0, "lgb": 1.0, "lstm": 1.0}


def _clip_probability(value: Any) -> float:
    try:
        return float(np.clip(float(value), 0.0, 1.0))
    except (TypeError, ValueError):
        return 0.5


class EnsemblePredictor:
    """Load all available validated models and produce one consensus.

    The loader is deliberately tolerant: a missing/broken optional model does
    not take down the whole ensemble.  At inference time every healthy model
    receives the exact same X payload.  Parallel inference can be enabled with
    AI_ENSEMBLE_CONCURRENCY=1 (default) or disabled with 0.
    """

    def __init__(self, symbol: str, timeframe: str, weights: dict[str, float] | None = None):
        self.symbol = symbol
        self.timeframe = timeframe
        self.models: dict[str, Any] = {}
        self.model_weights = dict(DEFAULT_WEIGHTS)
        if weights:
            self.model_weights.update({k: max(0.0, float(v)) for k, v in weights.items()})
        self._load_models()

    def _load_models(self) -> None:
        try:
            import joblib
        except Exception:
            joblib = None

        if joblib:
            for model_type in ("rf", "xgb", "lgb"):
                path = os.path.join(MODEL_DIR, f"{self.symbol}_{self.timeframe}_{model_type}.pkl")
                if not os.path.exists(path):
                    continue
                try:
                    self.models[model_type] = joblib.load(path)
                except Exception:
                    continue

        try:
            from tensorflow import keras
            path = os.path.join(MODEL_DIR, f"{self.symbol}_{self.timeframe}_lstm.keras")
            if os.path.exists(path):
                self.models["lstm"] = keras.models.load_model(path)
        except Exception:
            pass

    @staticmethod
    def _predict_one(model_type: str, model: Any, X: np.ndarray) -> float:
        if model_type == "lstm":
            # Keep compatibility with the existing one-row LSTM artifact.
            shaped = X.reshape(X.shape[0], -1, 1)
            raw = model.predict(shaped, verbose=0)
            return _clip_probability(np.asarray(raw).reshape(-1)[-1])
        if hasattr(model, "predict_proba"):
            raw = model.predict_proba(X)
            classes = list(getattr(model, "classes_", [0, 1]))
            if 1 in classes:
                return _clip_probability(raw[-1, classes.index(1)])
            return _clip_probability(raw[-1, -1])
        raw = model.predict(X)
        return _clip_probability(np.asarray(raw).reshape(-1)[-1])

    def _run_models(self, X: np.ndarray) -> list[dict[str, Any]]:
        if not self.models:
            return []

        def run(model_type: str, model: Any) -> dict[str, Any]:
            probability = self._predict_one(model_type, model, X)
            return {
                "model": model_type,
                "probability": probability,
                "weight": float(self.model_weights.get(model_type, 1.0)),
            }

        concurrent = os.environ.get("AI_ENSEMBLE_CONCURRENCY", "0") == "1"
        results: list[dict[str, Any]] = []
        if concurrent and len(self.models) > 1:
            with ThreadPoolExecutor(max_workers=min(len(self.models), 4)) as pool:
                futures = {pool.submit(run, name, model): name for name, model in self.models.items()}
                for future in as_completed(futures):
                    try:
                        results.append(future.result())
                    except Exception:
                        continue
        else:
            for name, model in self.models.items():
                try:
                    results.append(run(name, model))
                except Exception:
                    continue
        return results

    @staticmethod
    def consensus(predictions: list[dict[str, Any]], avoid_band: float = 0.10, min_confidence: float = 0.65) -> dict[str, Any]:
        """Aggregate probabilities and explicitly handle disagreement.

        BUY and SELL are represented by probability of an upward next move.
        AVOID is an abstention when the consensus is too close to 0.5.  The
        confidence is the probability distance from a 50/50 decision, adjusted
        by agreement, rather than a misleading average of raw confidences.
        """
        if not predictions:
            return {
                "decision": "AVOID", "direction": "NO_MODELS", "probability": 0.5,
                "confidence": 0.0, "agreement": 0.0, "models_used": 0,
                "model_types": [], "model_outputs": [], "reason": "No healthy models available",
            }

        usable = [p for p in predictions if float(p.get("weight", 0)) > 0]
        if not usable:
            usable = predictions
        weights = np.asarray([max(0.0, float(p.get("weight", 1.0))) for p in usable], dtype=float)
        probs = np.asarray([_clip_probability(p.get("probability", 0.5)) for p in usable], dtype=float)
        if weights.sum() <= 0:
            weights = np.ones_like(probs)
        consensus_prob = float(np.average(probs, weights=weights))
        std = float(np.sqrt(np.average((probs - consensus_prob) ** 2, weights=weights)))
        agreement = float(max(0.0, min(1.0, 1.0 - (std / 0.5))))

        # Directional strength is 0..1; agreement prevents conflicting models
        # from producing an artificially high trade confidence.
        strength = abs(consensus_prob - 0.5) * 2.0
        confidence = float(max(0.0, min(1.0, strength * (0.5 + 0.5 * agreement))))
        decision = "BUY" if consensus_prob > 0.5 else "SELL"
        if abs(consensus_prob - 0.5) < avoid_band or confidence < min_confidence:
            decision = "AVOID"

        return {
            "decision": decision,
            "direction": "UP" if consensus_prob > 0.5 else "DOWN" if consensus_prob < 0.5 else "FLAT",
            "probability": round(consensus_prob, 4),
            "confidence": round(confidence, 4),
            "agreement": round(agreement, 4),
            "std_dev": round(std, 4),
            "models_used": len(usable),
            "model_types": [p["model"] for p in usable],
            "model_outputs": usable,
        }

    def predict(self, X: np.ndarray) -> dict[str, Any]:
        predictions = self._run_models(np.asarray(X, dtype=float))
        result = self.consensus(
            predictions,
            avoid_band=float(os.environ.get("AI_ENSEMBLE_AVOID_BAND", "0.10")),
            min_confidence=float(os.environ.get("AI_ENSEMBLE_MIN_CONFIDENCE", "0.65")),
        )
        # Preserve the legacy contract used by InferenceService.
        return result
