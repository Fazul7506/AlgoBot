from rest_framework import decorators, permissions, response, status

from apps.indicators.basic_features import compute_basic_features
from apps.market_data.research import ResearchCandleStore
from .serializers import AIRecommendationSerializer, MarketRegimeSerializer, PredictionSerializer
from .services import AIEngine
from .validators import validate_feature_context


@decorators.api_view(["POST"])
@decorators.permission_classes([permissions.IsAuthenticated])
def research_predict(request):
    """Run AI research strictly from persisted canonical Candle rows.

    This endpoint deliberately has no broker-account dependency and never
    falls back to a live broker adapter. Live execution continues to use the
    separate broker-aware AI path.
    """
    symbol = str(request.data.get("symbol") or "").strip().upper()
    timeframe = str(request.data.get("timeframe") or "1m").strip()
    if not symbol:
        return response.Response(
            {"detail": "symbol is required", "code": "RESEARCH_SYMBOL_REQUIRED"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        timeframe = ResearchCandleStore.timeframe(timeframe)
        candles = ResearchCandleStore.candles(symbol, timeframe, limit=250)
    except ValueError as exc:
        return response.Response(
            {"detail": str(exc), "code": "RESEARCH_CANDLE_CONTEXT_INVALID"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if len(candles) < 25:
        return response.Response(
            {
                "detail": f"Insufficient persisted candles for {symbol}/{timeframe}: found {len(candles)}, need at least 25.",
                "code": "RESEARCH_CANDLE_HISTORY_INSUFFICIENT",
                "source": "market_data.Candle",
                "symbol": symbol,
                "timeframe": timeframe,
                "candles_available": len(candles),
            },
            status=status.HTTP_409_CONFLICT,
        )

    latest = candles[-1]
    indicator_rows = compute_basic_features(candles)
    indicators = indicator_rows[-1] if indicator_rows else {}
    context = validate_feature_context(
        {
            "market_data": {
                "open": float(latest["open"]),
                "high": float(latest["high"]),
                "low": float(latest["low"]),
                "close": float(latest["close"]),
                "volume": float(latest["volume"] or 0),
                "epoch": int(latest["epoch"]),
                "source": "persisted_candle_database",
            },
            "indicators": indicators,
            "candles": candles[-60:],
        }
    )

    try:
        result = AIEngine().analyze(symbol, timeframe, context)
        prediction = result["prediction"]
        recommendation = result["recommendation"]
        regime = result["regime"]
        prediction.user = request.user
        prediction.save(update_fields=["user"])
        recommendation.user = request.user
        recommendation.save(update_fields=["user"])
        regime.user = request.user
        regime.save(update_fields=["user"])
        return response.Response(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "source": "market_data.Candle",
                "candle_count": len(candles),
                "latest_epoch": int(latest["epoch"]),
                "prediction": PredictionSerializer(prediction).data,
                "recommendation": AIRecommendationSerializer(recommendation).data,
                "regime": MarketRegimeSerializer(regime).data,
                "explainability": result["explainability"],
            }
        )
    except Exception as exc:
        return response.Response(
            {"detail": str(exc), "code": "RESEARCH_AI_INFERENCE_FAILED"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
