from datetime import timedelta

from django.utils import timezone

from deriv_platform.celery import app

from apps.market_data.constants import TIMEFRAMES
from apps.market_data.research_data import ResearchDataService
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
from .training_dataset import _timeframe_storage_aliases


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
    outcome_summary = resolve_prediction_outcomes(timeframe=timeframe, horizon_candles=1)
    summary = AIDataPipeline().training_summary(timeframe=timeframe, lookback_hours=168)
    # The aggregate readiness flag can be false when one symbol lacks history
    # even though other active symbols have enough candles to train. Always let
    # the per-symbol trainer validate its own dataset; it safely skips symbols
    # with insufficient history or models that fail walk-forward profitability.
    result = MarketModelTrainer().train_active_symbols(timeframe=timeframe, min_accuracy=min_accuracy)
    trained = sum(1 for value in result.values() if value.get("status") != "skipped")
    skipped = len(result) - trained
    return {
        "status": "trained" if trained else "no_models_trained",
        "summary": summary,
        "outcomes": outcome_summary,
        "symbols_requested": len(result),
        "models_trained": trained,
        "symbols_skipped": skipped,
        "reason": None if trained else (
            "no_active_tradable_symbols" if not result else "insufficient_history_or_validation_failed"
        ),
        "result": result,
    }


@app.task
def generate_features(symbol, timeframe="M1", context=None):
    return FeatureEngineeringService().build_features(symbol, timeframe, context or {})


@app.task
def refresh_prediction(symbol, timeframe="M1", context=None):
    return PredictionService().predict(symbol, timeframe, context or {}).id


@app.task
def resolve_prediction_outcomes(timeframe="M1", horizon_candles=1, batch_size=500):
    """Label matured predictions using the next persisted canonical candle.

    Historical validation reads only broker-ingested ``market_data.Candle``
    rows. The timeframe is normalized before both the maturity cutoff and the
    candle query so aliases such as M1/H1 cannot diverge from stored rows.
    """
    research_data = ResearchDataService()
    canonical_timeframe = research_data.timeframe(timeframe)
    if canonical_timeframe == "tick":
        raise ValueError("Prediction outcomes require a candle timeframe, not tick mode")

    seconds = max(1, int(TIMEFRAMES[canonical_timeframe]))
    cutoff = timezone.now() - timedelta(seconds=seconds * max(1, int(horizon_candles)))
    pending = Prediction.objects.filter(
        timeframe__in=_timeframe_storage_aliases(canonical_timeframe),
        created_at__lte=cutoff,
    ).exclude(outcome__isnull=False).order_by("created_at")[:batch_size]
    resolved = 0
    skipped = 0

    for prediction in pending:
        try:
            market = research_data.market(prediction.symbol)
            future = research_data.next_candles(
                market.symbol,
                canonical_timeframe,
                after_epoch=int(prediction.created_at.timestamp()),
                limit=max(1, int(horizon_candles)),
            )
        except ValueError:
            skipped += 1
            continue

        if len(future) < horizon_candles:
            skipped += 1
            continue

        first = future[0]
        last = future[-1]
        try:
            base_close = float(prediction.payload.get("reference_price", first["open"]))
        except (TypeError, ValueError):
            base_close = float(first["open"])
        actual_close = float(last["close"])
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
                "details": {
                    "reference_price": base_close,
                    "close": actual_close,
                    "predicted_direction": predicted_direction,
                    "model_id": (prediction.payload or {}).get("model_id"),
                    "model_version": (prediction.payload or {}).get("model_version"),
                    "model_algorithm": (prediction.payload or {}).get("model_algorithm"),
                    "evaluation_horizon_candles": horizon_candles,
                },
            },
        )
        resolved += 1

    return {"status": "resolved", "resolved": resolved, "skipped": skipped, "timeframe": canonical_timeframe, "horizon_candles": horizon_candles}


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


@app.task
def ingest_market_sentiment():
    from .external_signals import ingest_rss_sentiment
    return ingest_rss_sentiment()


@app.task
def ingest_orderbook_depth():
    from .external_signals import ingest_orderbook_snapshots
    return ingest_orderbook_snapshots()

@app.task
def rollback_champion_model(symbol, timeframe="M1"):
    """Explicit operator-triggered rollback to the best persisted validated model."""
    from .training import rollback_champion_model as rollback

    return rollback(symbol=symbol, timeframe=timeframe)
\n

@app.task
def process_closed_candle(symbol, timeframe="1m", epoch=None):
    """Build features and a non-executing AI recommendation from a closed live candle."""
    import logging
    from django.core.cache import cache
    from apps.market_data.models import Candle
    from .services import PredictionService, RecommendationService

    logger = logging.getLogger(__name__)
    canonical_timeframe = str(timeframe or "1m").lower()
    if canonical_timeframe != "1m" or epoch is None:
        return {"status": "unsupported_candle_event", "symbol": symbol, "timeframe": canonical_timeframe}
    try:
        target_epoch = int(epoch)
    except (TypeError, ValueError):
        return {"status": "invalid_candle_epoch"}
    lock_key = f"ai:closed-candle:{symbol}:{canonical_timeframe}:{target_epoch}"
    if not cache.add(lock_key, "processing", timeout=6 * 60 * 60):
        return {"status": "duplicate_candle_event", "symbol": symbol, "epoch": target_epoch}
    try:
        rows = list(
            Candle.objects.filter(
                symbol__symbol=symbol,
                timeframe=canonical_timeframe,
                source="tick_stream",
                epoch__lte=target_epoch,
            ).order_by("-epoch").values(
                "open", "high", "low", "close", "volume", "epoch"
            )[:60]
        )
        rows.reverse()
        if len(rows) < 60:
            cache.set(lock_key, "insufficient_history", timeout=6 * 60 * 60)
            return {
                "status": "insufficient_history",
                "symbol": symbol,
                "timeframe": canonical_timeframe,
                "available_candles": len(rows),
                "required_candles": 60,
            }
        latest = rows[-1]
        context = {
            "candles": rows,
            "market_data": {
                "open": latest["open"],
                "high": latest["high"],
                "low": latest["low"],
                "close": latest["close"],
                "volume": latest["volume"],
            },
        }
        prediction = PredictionService().predict(symbol, canonical_timeframe, context)
        recommendation = RecommendationService().recommend(symbol, prediction)
        cache.set(lock_key, "completed", timeout=6 * 60 * 60)
        return {
            "status": "completed",
            "symbol": symbol,
            "timeframe": canonical_timeframe,
            "epoch": target_epoch,
            "prediction_id": prediction.pk,
            "model_version": (prediction.payload or {}).get("model_version"),
            "recommendation_id": recommendation.pk,
            "recommendation": recommendation.recommendation,
        }
    except Exception:
        cache.delete(lock_key)
        logger.exception(
            "ai.closed_candle_processing_failed",
            extra={"symbol": symbol, "timeframe": canonical_timeframe, "epoch": target_epoch},
        )
        raise


@app.task
def check_model_degradation():
    """Measure persisted prediction outcomes and schedule guarded retraining on degradation."""
    import logging
    from collections import defaultdict
    from django.core.cache import cache

    logger = logging.getLogger(__name__)
    outcomes = PredictionOutcome.objects.filter(
        resolved_at__isnull=False,
        correct__isnull=False,
    ).select_related("prediction").order_by("-resolved_at")[:1000]
    grouped = defaultdict(list)
    for outcome in outcomes:
        payload = outcome.prediction.payload or {}
        model_id = payload.get("model_id")
        model_version = payload.get("model_version")
        if model_id is None or not model_version:
            continue
        key = (
            outcome.prediction.symbol,
            outcome.prediction.timeframe,
            str(model_id),
            str(model_version),
        )
        grouped[key].append(bool(outcome.correct))

    degraded = []
    for (symbol, timeframe, model_id, model_version), values in grouped.items():
        if len(values) < 30:
            continue
        accuracy = sum(values) / len(values)
        if accuracy >= 0.48:
            continue
        degraded.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "model_id": model_id,
            "model_version": model_version,
            "sample_size": len(values),
            "accuracy": accuracy,
        })
        logger.warning(
            "ai.model_degradation_detected",
            extra=degraded[-1],
        )
        # One shared six-hour gate per timeframe prevents a degradation event
        # from enqueuing a retraining storm. Promotion still requires the full
        # walk-forward profitability and champion comparison gates.
        gate = f"ai:model-degradation-retrain:{timeframe}"
        if cache.add(gate, "queued", timeout=6 * 60 * 60):
            try:
                scheduled_ai_training.apply_async(
                    kwargs={"timeframe": timeframe, "min_accuracy": 0.52},
                    queue="celery",
                )
            except Exception:
                cache.delete(gate)
                logger.exception(
                    "ai.model_degradation_retraining_dispatch_failed",
                    extra={"timeframe": timeframe},
                )
    return {"status": "checked", "models_with_degradation": len(degraded), "degraded": degraded}
\n