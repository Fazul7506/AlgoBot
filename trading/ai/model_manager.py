"""
Model management utilities for comparing models and persisting retraining metadata.
"""
import os
from typing import Dict, List, Optional
from django.utils import timezone
from trading.models.core import AIModel

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')
os.makedirs(MODEL_DIR, exist_ok=True)


class ModelManager:
    """Lookup and compare trained AI models for a symbol/timeframe."""

    @staticmethod
    def _score_metrics(metrics: Dict[str, object], trained_at=None) -> float:
        accuracy = float(metrics.get('accuracy', 0.0))
        win_rate = float(metrics.get('win_rate', 0.0))
        n_samples = float(metrics.get('n_samples', 0.0))
        freshness = 0.0
        if trained_at:
            age_days = (timezone.now() - trained_at).total_seconds() / 86400.0
            freshness = max(0.0, 1.0 - min(age_days, 30.0) / 30.0)

        return accuracy * 0.5 + win_rate * 0.3 + min(1.0, n_samples / 1000.0) * 0.1 + freshness * 0.1

    @staticmethod
    def list_models(symbol: str, timeframe: str) -> List[AIModel]:
        prefix = f"{symbol}_{timeframe}_"
        return list(AIModel.objects.filter(name__startswith=prefix).order_by('-trained_at', '-created_at'))

    @staticmethod
    def compare_models(symbol: str, timeframe: str) -> List[Dict[str, object]]:
        models = ModelManager.list_models(symbol, timeframe)
        summary = []

        for model in models:
            metrics = model.metrics or {}
            trained_at = model.trained_at
            score = ModelManager._score_metrics(metrics, trained_at=trained_at)
            summary.append({
                'name': model.name,
                'model_type': model.model_type,
                'storage_path': model.storage_path,
                'version': model.version,
                'trained_at': trained_at.isoformat() if trained_at else None,
                'metrics': metrics,
                'score': round(score, 4),
            })

        return sorted(summary, key=lambda item: item['score'], reverse=True)

    @staticmethod
    def best_model(symbol: str, timeframe: str) -> Optional[Dict[str, object]]:
        ranked = ModelManager.compare_models(symbol, timeframe)
        return ranked[0] if ranked else None

    @staticmethod
    def model_path(symbol: str, timeframe: str, model_type: str) -> str:
        if model_type == 'lstm':
            return os.path.join(MODEL_DIR, f'{symbol}_{timeframe}_lstm.keras')
        return os.path.join(MODEL_DIR, f'{symbol}_{timeframe}_{model_type}.pkl')


class ModelRecordUpdater:
    """Create or update AIModel registry records."""

    @staticmethod
    def upsert_model_record(
        name: str,
        model_type: str,
        storage_path: str,
        metrics: Dict[str, object],
    ) -> AIModel:
        existing = AIModel.objects.filter(name=name).first()
        if existing:
            version = existing.version
            if version.isdigit():
                version = str(int(version) + 1)
            else:
                version = str(existing.version) if existing.version else '1'

            existing.storage_path = storage_path
            existing.model_type = model_type
            existing.version = version
            existing.trained_at = timezone.now()
            existing.metrics = metrics or {}
            existing.save(update_fields=['storage_path', 'model_type', 'version', 'trained_at', 'metrics'])
            return existing

        return AIModel.objects.create(
            name=name,
            model_type=model_type,
            storage_path=storage_path,
            version='1',
            trained_at=timezone.now(),
            metrics=metrics or {},
        )
