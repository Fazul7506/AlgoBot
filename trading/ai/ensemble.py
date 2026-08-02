"""
Ensemble predictor combining Random Forest, XGBoost, and LSTM models.
"""
import os
import numpy as np
from typing import Dict, Any, List

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')


class EnsemblePredictor:
    def __init__(self, symbol: str, timeframe: str):
        self.symbol = symbol
        self.timeframe = timeframe
        self.models = {}
        self._load_models()

    def _load_models(self):
        """Load all available trained models for this symbol/timeframe."""
        try:
            import joblib
            for model_type in ['rf', 'xgb', 'lgb']:
                path = os.path.join(MODEL_DIR, f'{self.symbol}_{self.timeframe}_{model_type}.pkl')
                if os.path.exists(path):
                    self.models[model_type] = joblib.load(path)
        except Exception:
            pass

        # Try to load LSTM
        try:
            from tensorflow import keras
            lstm_path = os.path.join(MODEL_DIR, f'{self.symbol}_{self.timeframe}_lstm.keras')
            if os.path.exists(lstm_path):
                self.models['lstm'] = keras.models.load_model(lstm_path)
        except Exception:
            pass

    def predict(self, X) -> Dict[str, Any]:
        """Ensemble prediction combining all available models."""
        if not self.models:
            return {
                'direction': 'NO_MODELS',
                'probability': 0.0,
                'confidence': 0.0,
                'models_used': 0
            }

        probs = []
        models_used = []

        for model_type, model in self.models.items():
            try:
                if model_type == 'lstm':
                    # LSTM expects sequences
                    if len(X.shape) == 1:
                        X_reshaped = X.reshape(1, -1, 1)
                    else:
                        X_reshaped = X.reshape(X.shape[0], -1, 1)
                    prob = model.predict(X_reshaped, verbose=0)
                    probs.append(float(prob[-1, 0]))
                else:
                    # sklearn models
                    if hasattr(model, 'predict_proba'):
                        p = model.predict_proba(X)
                        probs.append(float(p[-1, 1]))
                    else:
                        pred = model.predict(X)
                        probs.append(float(pred[-1]))
                models_used.append(model_type)
            except Exception:
                continue

        if not probs:
            return {
                'direction': 'ERROR',
                'probability': 0.0,
                'confidence': 0.0,
                'models_used': 0
            }

        avg_prob = np.mean(probs)
        std_prob = np.std(probs)
        
        # Higher agreement = higher confidence
        agreement_bonus = max(0, 0.2 * (1 - std_prob))
        confidence = min(1.0, avg_prob + agreement_bonus)

        return {
            'direction': 'UP' if avg_prob > 0.5 else 'DOWN',
            'probability': round(avg_prob, 3),
            'confidence': round(confidence, 3),
            'models_used': len(models_used),
            'model_types': models_used,
            'std_dev': round(std_prob, 3)
        }
