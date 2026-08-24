from deriv_platform.celery import app

from .services import (
    AnomalyDetectionService,
    EnsembleService,
    FeatureEngineeringService,
    HyperparameterOptimizationService,
    PredictionService,
)
from .training import MarketModelTrainer


@app.task
def train_model(model_id=None, timeframe="M1", min_accuracy=0.52):
    """Train and publish validated models from persisted market candles."""
    if model_id:
        from .models import AIModel
        model = AIModel.objects.get(pk=model_id)
        # Keep the task compatible with the existing admin/manual workflow.
        return MarketModelTrainer().train_symbol(model.name.split("-")[0], timeframe, min_accuracy)
    return MarketModelTrainer().train_active_symbols(timeframe=timeframe, min_accuracy=min_accuracy)


@app.task
def generate_features(symbol, timeframe="M1", context=None):
    return FeatureEngineeringService().build_features(symbol, timeframe, context or {})


@app.task
def refresh_prediction(symbol, timeframe="M1", context=None):
    return PredictionService().predict(symbol, timeframe, context or {}).id


@app.task
def optimize_hyperparameters(algorithm, search="random_search"):
    return HyperparameterOptimizationService().optimize(algorithm, search)


@app.task
def recalculate_ensemble(predictions):
    return EnsembleService().combine(predictions)


@app.task
def scan_anomalies(symbol, features):
    obj = AnomalyDetectionService().scan(symbol, features)
    return obj.id if obj else None


@app.task
def evaluate_model(model_id):
    return {"model_id": model_id, "status": "evaluated"}


@app.task
def compare_champion_challenger():
    return {"status": "compared"}
