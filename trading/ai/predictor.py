"""
Prediction engine that loads models and returns direction + probability + confidence.
Supports sklearn-style `predict_proba` models and returns a structured dict.
"""
import os
import json
from typing import Dict, Any

import numpy as np

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')


class Predictor:
    def __init__(self, model_name: str = 'rf.pkl'):
        self.model_path = os.path.join(MODEL_DIR, model_name)
        self.model = None
        self._load()

    def _load(self):
        if not os.path.exists(self.model_path):
            return
        try:
            import joblib
            self.model = joblib.load(self.model_path)
        except Exception:
            self.model = None

    def predict(self, X) -> Dict[str, Any]:
        """Return dict: {'direction','probability','confidence'}"""
        if self.model is None:
            return {'direction': 'NO_MODEL', 'probability': 0.0, 'confidence': 0.0}

        try:
            if hasattr(self.model, 'predict_proba'):
                proba = self.model.predict_proba(X)
                # assume binary [0,1]
                probs = proba[:, 1]
                direction = ['DOWN','UP']
                idx = int(round(probs[-1])) if len(probs)>0 else 0
                return {
                    'direction': direction[idx],
                    'probability': float(probs[-1]) if len(probs)>0 else 0.0,
                    'confidence': float(probs[-1])
                }
            else:
                pred = self.model.predict(X)
                return {'direction': 'UP' if pred[-1]==1 else 'DOWN', 'probability': 0.5, 'confidence': 0.5}
        except Exception:
            return {'direction': 'ERROR', 'probability': 0.0, 'confidence': 0.0}
