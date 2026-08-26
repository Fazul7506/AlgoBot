from datetime import timedelta

from django.utils import timezone

from deriv_platform.celery import app

from .data_pipeline import AIDataPipeline
from .models import Prediction, PredictionOutcome
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
        return MarketModelTrainer().train_symbol(model.name.split("-")[0], timeframe, min_accuracy)
    return MarketModelTrainer().train_active_symbols(timeframe=timeframe, min_accuracy=min_accuracy)


@app.task
def refresh_ai_data(timeframe="M1", lookback_hours=168):
    return AIDataPipeline().training_summary(timeframe, lookback_hours)


@app.task
def check_ai_data_health(timeframe="M1"):
    return AIDataPipeline().health(timeframe)


@app.task
def scheduled_ai_training(timeframe="M1", min_accuracy=0.52):
    """Train active symbols only when canonical market data is ready."""
    summary = AIDataPipeline().training_summary(timeframe=timeframe, lookback_hours=168)
    if not summary["ready"]:
        return {"status": "skipped", "reason": "no_market_data", "summary": summary}
    result = MarketModelTrainer().train_active_symbols(timeframe=timeframe, min_accuracy=min_accuracy)
    return {"status": "trained", "summary": summary, "result": result}


@app.task
def generate_features(symbol, timeframe="M1", context=None):
    return FeatureEngineeringService().build_features(symbol, timeframe, context or {})


@app.task
def refresh_prediction(symbol, timeframe="M1", context=None):
    return PredictionService().predict(symbol, timeframe, context or {}).id


@app.task
def resolve_prediction_outcomes(timeframe="M1", horizon_candles=1, batch_size=500):
    """Label matured predictions using the next persisted candle.

    This creates the feedback dataset without allowing future candles to leak
    into the original prediction. Only predictions old enough to have a full
    horizon are resolved.
    """
    from apps.market_data.models import Candle, MarketSymbol

    cutoff = timezone.now() - timedelta(minutes=max(1, horizon_candles))
    pending = Prediction.objects.filter(timeframe=timeframe, created_at__lte=cutoff).exclude(outcome__isnull=False).order_by("created_at")[:batch_size]
    resolved = 0
    skipped = 0

    for prediction in pending:
        symbol = MarketSymbol.objects.filter(symbol=prediction.symbol, is_active=True).first()
        if not symbol:
            skipped += 1
            continue

        future = list(
            Candle.objects.filter(symbol=symbol, timeframe=timeframe, created_at__gt=prediction.created_at)
            .order_by("epoch")[:horizon_candles]
        )
        if len(future) < horizon_candles:
            skipped += 1
            continue

        first = future[0]
        last = future[-1]
        try:
            base_close = float(prediction.payload.get("reference_price", first.open))
        except (TypeError, ValueError):
            base_close = float(first.open)
        actual_close = float(last.close)
        actual_return = (actual_close - base_close) / base_close if base_close else 0.0
        actual_direction = "UP" if actual_return > 0 else "DOWN" if actual_return < 0 else "FLAT"
        predicted = str(prediction.prediction).upper()
        predicted_direction = "UP" if predicted in {"BUY", "LONG", "UP"} else "DOWN" if predicted in {"SELL", "SHORT", "DOWN"} else "FLAT"

        PredictionOutcome.objects.update_or_create(
            prediction=prediction,
            defaults={
                "actual_direction": actual_direction,
                "actual_return": actual_return,
                "correct": predicted_direction == actual_direction,
                "horizon_candles": horizon_candles,
                "resolved_at": timezone.now(),
                "details": {"reference_price": base_close, "close": actual_close, "predicted_direction": predicted_direction},
            },
        )
        resolved += 1

    return {"status": "resolved", "resolved": resolved, "skipped": skipped, "timeframe": timeframe, "horizon_candles": horizon_candles}


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
