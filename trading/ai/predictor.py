"""Production-safe model inference with explicit uncertainty handling."""
import os
from typing import Any, Dict

import numpy as np

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')


class Predictor:
    """Load a persisted model and expose normalized prediction metadata.

    The predictor never invents a probability when the model cannot provide one.
    """

    def __init__(self, model_name: str = 'rf.pkl'):
        self.model_path = os.path.join(MODEL_DIR, model_name)
        self.model = None
        self.model_name = model_name
        self._load()

    def _load(self) -> None:
        if not os.path.isfile(self.model_path):
            return
        try:
            import joblib
            self.model = joblib.load(self.model_path)
        except Exception:
            self.model = None

    @staticmethod
    def _direction_from_label(label: Any) -> str:
        value = str(label).upper()
        if value in {'1', 'UP', 'BUY', 'LONG', 'CALL'}:
            return 'UP'
        if value in {'0', '-1', 'DOWN', 'SELL', 'SHORT', 'PUT'}:
            return 'DOWN'
        return value

    def predict(self, X) -> Dict[str, Any]:
        if self.model is None:
            return {'direction': 'NO_MODEL', 'probability': 0.0, 'confidence': 0.0, 'uncertainty': 1.0, 'model': self.model_name}
        try:
            if hasattr(self.model, 'predict_proba'):
                probabilities = np.asarray(self.model.predict_proba(X), dtype=float)
                if probabilities.ndim != 2 or probabilities.shape[0] == 0:
                    raise ValueError('Model returned invalid probability shape')
                row = np.clip(probabilities[-1], 0.0, 1.0)
                total = float(row.sum())
                if total <= 0:
                    raise ValueError('Model returned zero probability mass')
                row /= total
                classes = list(getattr(self.model, 'classes_', range(len(row))))
                best_index = int(np.argmax(row))
                best_probability = float(row[best_index])
                direction = self._direction_from_label(classes[best_index])
                if direction not in {'UP', 'DOWN'} and len(row) == 2:
                    direction = 'UP' if best_index == 1 else 'DOWN'
                entropy = float(-(row * np.log(np.clip(row, 1e-12, 1.0))).sum())
                max_entropy = float(np.log(len(row))) if len(row) > 1 else 1.0
                uncertainty = min(1.0, entropy / max_entropy) if max_entropy else 0.0
                confidence = max(0.0, min(1.0, best_probability * (1.0 - uncertainty)))
                return {'direction': direction, 'probability': best_probability, 'confidence': confidence, 'uncertainty': uncertainty, 'class_probabilities': {str(c): float(p) for c, p in zip(classes, row)}, 'model': self.model_name}

            if hasattr(self.model, 'predict'):
                prediction = np.asarray(self.model.predict(X)).reshape(-1)
                if prediction.size == 0:
                    raise ValueError('Model returned no predictions')
                direction = self._direction_from_label(prediction[-1])
                if direction not in {'UP', 'DOWN'}:
                    direction = 'UP' if str(prediction[-1]) in {'1', 'BUY', 'LONG', 'CALL'} else 'DOWN'
                # Point predictions carry no calibrated probability; expose neutral confidence.
                return {'direction': direction, 'probability': 0.0, 'confidence': 0.0, 'uncertainty': 1.0, 'probability_source': 'unavailable', 'model': self.model_name}

            return {'direction': 'UNSUPPORTED_MODEL', 'probability': 0.0, 'confidence': 0.0, 'uncertainty': 1.0, 'model': self.model_name}
        except Exception as exc:
            return {'direction': 'ERROR', 'probability': 0.0, 'confidence': 0.0, 'uncertainty': 1.0, 'error': str(exc), 'model': self.model_name}
