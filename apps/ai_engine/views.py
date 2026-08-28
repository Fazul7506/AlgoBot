import asyncio
from datetime import timedelta

from django.db.models import Count, Avg
from django.utils import timezone
from rest_framework import viewsets, permissions, decorators, response, status
from apps.market_data.models import MarketSymbol
from apps.brokers.models import BrokerAccount
from apps.brokers.services import BrokerRegistry
from .models import AIModel, ModelVersion, Prediction, PredictionOutcome, FeatureVector, TrainingJob, AIRecommendation, MarketRegime, AnomalyEvent
from .serializers import *
from .services import AIEngine, TrainingService, ExplainabilityService, FeatureStoreService
from .validators import validate_feature_context


class _UserScoped:
    permission_classes = [permissions.IsAuthenticated]
    def _owned(self, qs):
        return qs


class AIModelViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AIModel.objects.all(); serializer_class = AIModelSerializer; permission_classes = [permissions.IsAuthenticated]
class ModelVersionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ModelVersion.objects.select_related("model").all(); serializer_class = ModelVersionSerializer; permission_classes = [permissions.IsAuthenticated]
class PredictionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Prediction.objects.all(); serializer_class = PredictionSerializer; permission_classes = [permissions.IsAuthenticated]
class RecommendationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AIRecommendation.objects.all(); serializer_class = AIRecommendationSerializer; permission_classes = [permissions.IsAuthenticated]
class MarketRegimeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MarketRegime.objects.all(); serializer_class = MarketRegimeSerializer; permission_classes = [permissions.IsAuthenticated]
class FeatureVectorViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = FeatureVector.objects.all(); serializer_class = FeatureVectorSerializer; permission_classes = [permissions.IsAuthenticated]
class AnomalyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AnomalyEvent.objects.all(); serializer_class = AnomalyEventSerializer; permission_classes = [permissions.IsAuthenticated]
class TrainingJobViewSet(viewsets.ModelViewSet):
    queryset = TrainingJob.objects.all(); serializer_class = TrainingJobSerializer; permission_classes = [permissions.IsAuthenticated]


@decorators.api_view(["GET"])
@decorators.permission_classes([permissions.IsAuthenticated])
def model_governance(request):
    model_id = request.query_params.get("model_id")
    versions = ModelVersion.objects.select_related("model")
    if model_id:
        versions = versions.filter(model_id=model_id)
    recent_cutoff = timezone.now() - timedelta(days=30)
    predictions = Prediction.objects.filter(created_at__gte=recent_cutoff)
    resolved = PredictionOutcome.objects.filter(prediction__in=predictions, correct__isnull=False)
    total = resolved.count()
    correct = resolved.filter(correct=True).count()
    accuracy = (correct / total) if total else None
    calibration = None
    if total:
        calibration = {
            "sample_size": total,
            "accuracy": round(accuracy, 6),
            "mean_confidence": round(float(resolved.aggregate(v=Avg("prediction__confidence"))["v"] or 0), 6),
            "status": "available",
        }
    else:
        calibration = {"sample_size": 0, "accuracy": None, "mean_confidence": None, "status": "insufficient_data"}
    latest_features = FeatureVector.objects.filter(timestamp__gte=recent_cutoff).count()
    previous_features = FeatureVector.objects.filter(timestamp__lt=recent_cutoff, timestamp__gte=recent_cutoff - timedelta(days=30)).count()
    drift = {
        "status": "available" if latest_features and previous_features else "insufficient_data",
        "recent_feature_vectors": latest_features,
        "previous_period_feature_vectors": previous_features,
    }
    return response.Response({
        "models": AIModelSerializer(AIModel.objects.all(), many=True).data,
        "versions": ModelVersionSerializer(versions, many=True).data,
        "calibration": calibration,
        "drift": drift,
        "governance": {"live_trading_authority": False, "role": "research_and_advisory"},
    })


@decorators.api_view(["POST"])
@decorators.permission_classes([permissions.IsAuthenticated])
def train(request):
    try:
        job = TrainingService().train(mode=request.data.get("mode", "manual"))
        return response.Response(TrainingJobSerializer(job).data, status=status.HTTP_201_CREATED)
    except Exception as exc:
        return response.Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


def _discover_symbol(request):
    symbol = str(request.data.get("symbol") or "").strip()
    if symbol:
        if not MarketSymbol.objects.filter(symbol=symbol, is_active=True, is_tradable=True).exists():
            raise ValueError("The selected symbol is not an active broker instrument.")
        return symbol
    return MarketSymbol.objects.filter(is_active=True, is_tradable=True).values_list("symbol", flat=True).first()


def _connected_account(user):
    return (BrokerAccount.objects.filter(user=user, status="active", broker__status="active").select_related("broker").order_by("-is_preferred", "-id").first())


async def _bounded_market_data(account, symbol):
    adapter = BrokerRegistry().adapter(account.broker, account)
    return await asyncio.wait_for(adapter.get_market_data(symbol), timeout=7.0)


@decorators.api_view(["POST"])
@decorators.permission_classes([permissions.IsAuthenticated])
def predict(request):
    symbol = _discover_symbol(request)
    if not symbol: return response.Response({"detail": "No active broker market is available. Connect a broker and synchronize markets first.", "code": "NO_ACTIVE_MARKET"}, status=status.HTTP_409_CONFLICT)
    account = _connected_account(request.user)
    if not account: return response.Response({"detail": "Connect a broker before requesting AI analysis.", "code": "NO_CONNECTED_BROKER"}, status=status.HTTP_409_CONFLICT)
    timeframe = str(request.data.get("timeframe") or "M1").upper()
    try:
        raw_context = request.data.get("context") or {}
        if not raw_context.get("market_data"):
            tick = asyncio.run(_bounded_market_data(account, symbol))
            raw_context["market_data"] = {"close": tick.get("price", tick.get("quote")), "open": tick.get("price", tick.get("quote")), "high": tick.get("price", tick.get("quote")), "low": tick.get("price", tick.get("quote")), "bid": tick.get("bid"), "ask": tick.get("ask"), "spread": (tick.get("ask") - tick.get("bid")) if tick.get("ask") is not None and tick.get("bid") is not None else 0}
        ctx = validate_feature_context(raw_context)
        result = AIEngine().analyze(symbol, timeframe, ctx)
        return response.Response({"symbol": symbol, "timeframe": timeframe, "broker": account.broker.name, "account_id": account.account_id, "prediction": PredictionSerializer(result["prediction"]).data, "recommendation": AIRecommendationSerializer(result["recommendation"]).data, "regime": MarketRegimeSerializer(result["regime"]).data, "explainability": result["explainability"]})
    except (ValueError, TypeError) as exc: return response.Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except asyncio.TimeoutError: return response.Response({"detail": "Connected broker market data timed out; the last known data was not fabricated.", "code": "BROKER_MARKET_DATA_TIMEOUT"}, status=status.HTTP_504_GATEWAY_TIMEOUT)
    except Exception as exc: return response.Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@decorators.api_view(["GET"])
@decorators.permission_classes([permissions.IsAuthenticated])
def explain(request):
    symbol = str(request.query_params.get("symbol") or "").strip(); timeframe = str(request.query_params.get("timeframe") or "M1").upper()
    if not symbol: return response.Response({"detail": "symbol is required"}, status=status.HTTP_400_BAD_REQUEST)
    features = FeatureStoreService().latest(symbol, timeframe)
    if not features: return response.Response({"detail": "No AI feature vector is available for this market yet."}, status=status.HTTP_404_NOT_FOUND)
    return response.Response(ExplainabilityService().explain(features))
