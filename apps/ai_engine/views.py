import asyncio
from datetime import timedelta

from django.conf import settings
from django.db.models import Avg
from django.utils import timezone
from rest_framework import viewsets, permissions, decorators, response, status
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.market_data.models import MarketSymbol, Tick, Candle
from apps.brokers.models import BrokerAccount
from apps.brokers.services import BrokerRegistry
from .models import AIModel, ModelVersion, Prediction, PredictionOutcome, FeatureVector, TrainingJob, AIRecommendation, MarketRegime, AnomalyEvent
from .serializers import *
from .services import AIEngine, TrainingService, ExplainabilityService, FeatureStoreService
from .validators import validate_feature_context


class JWTAuthenticatedPermission(permissions.IsAuthenticated):
    """Fail closed for browser/API AI requests instead of querying with AnonymousUser."""
    message = "Authentication credentials are required for AI analysis."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class _UserScoped:
    permission_classes = [JWTAuthenticatedPermission]

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
@decorators.permission_classes([JWTAuthenticatedPermission])
@decorators.authentication_classes([SessionAuthentication, JWTAuthentication])
def model_governance(request):
    model_id = request.query_params.get("model_id")
    versions = ModelVersion.objects.select_related("model")
    if model_id: versions = versions.filter(model_id=model_id)
    recent_cutoff = timezone.now() - timedelta(days=30)
    predictions = Prediction.objects.filter(created_at__gte=recent_cutoff)
    resolved = PredictionOutcome.objects.filter(prediction__in=predictions, correct__isnull=False)
    total = resolved.count(); correct = resolved.filter(correct=True).count(); accuracy = (correct / total) if total else None
    calibration = {"sample_size": total, "accuracy": round(accuracy, 6) if accuracy is not None else None, "mean_confidence": round(float(resolved.aggregate(v=Avg("prediction__confidence"))["v"] or 0), 6) if total else None, "status": "available" if total else "insufficient_data"}
    latest_features = FeatureVector.objects.filter(timestamp__gte=recent_cutoff).count()
    previous_features = FeatureVector.objects.filter(timestamp__lt=recent_cutoff, timestamp__gte=recent_cutoff - timedelta(days=30)).count()
    drift = {"status": "available" if latest_features and previous_features else "insufficient_data", "recent_feature_vectors": latest_features, "previous_period_feature_vectors": previous_features}
    return response.Response({"models": AIModelSerializer(AIModel.objects.all(), many=True).data, "versions": ModelVersionSerializer(versions, many=True).data, "calibration": calibration, "drift": drift, "governance": {"live_trading_authority": False, "role": "research_and_advisory"}})


@decorators.api_view(["POST"])
@decorators.permission_classes([JWTAuthenticatedPermission])
@decorators.authentication_classes([SessionAuthentication, JWTAuthentication])
def train(request):
    try:
        job = TrainingService().train(mode=request.data.get("mode", "manual"))
        return response.Response(TrainingJobSerializer(job).data, status=status.HTTP_201_CREATED)
    except Exception as exc:
        return response.Response({"detail": str(exc), "code": "AI_TRAINING_UNAVAILABLE"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


def _discover_symbol(request):
    symbol = str(request.data.get("symbol") or "").strip()
    if symbol:
        if not MarketSymbol.objects.filter(symbol=symbol, is_active=True, is_tradable=True).exists():
            raise ValueError("The selected symbol is not an active broker instrument.")
        return symbol
    return MarketSymbol.objects.filter(is_active=True, is_tradable=True).values_list("symbol", flat=True).first()


def _connected_account(user):
    return BrokerAccount.objects.filter(user=user, status="active", broker__status="active").select_related("broker").order_by("-is_preferred", "-id").first()


async def _bounded_market_data(account, symbol):
    adapter = BrokerRegistry().adapter(account.broker, account)
    return await asyncio.wait_for(adapter.get_market_data(symbol), timeout=7.0)


def _persisted_market_context(symbol, timeframe):
    """Return fresh broker-ingested data only; never use browser-provided market data."""
    max_age = int(getattr(settings, "BROKER_MARKET_DATA_MAX_AGE_SECONDS", 30)); now = timezone.now()
    tick = Tick.objects.filter(symbol__symbol=symbol).order_by("-epoch", "-received_at").first()
    candles = list(reversed(list(Candle.objects.filter(symbol__symbol=symbol, timeframe=timeframe).order_by("-epoch")[:60])))
    if tick is None: return None
    age = max(0, (now - tick.received_at).total_seconds())
    if age > max_age: return None
    price = float(tick.quote)
    return {"market_data":{"close":price,"open":price,"high":price,"low":price,"bid":float(tick.bid) if tick.bid is not None else None,"ask":float(tick.ask) if tick.ask is not None else None,"spread":float(tick.spread or 0),"volume":float(tick.volume or 0),"source":"persisted_broker_tick","age_seconds":round(age,3)},"candles":[{"open":float(c.open),"high":float(c.high),"low":float(c.low),"close":float(c.close),"volume":float(c.volume or 0),"epoch":c.epoch} for c in candles]}


def _broker_market_context(account, symbol):
    tick = asyncio.run(_bounded_market_data(account, symbol)); price = tick.get("price", tick.get("quote"))
    if price is None: raise ValueError("Broker returned no usable market price for the selected symbol.")
    return {"market_data":{"close":price,"open":price,"high":price,"low":price,"bid":tick.get("bid"),"ask":tick.get("ask"),"spread":(tick.get("ask")-tick.get("bid")) if tick.get("ask") is not None and tick.get("bid") is not None else 0,"source":"live_broker_tick"}}


@decorators.api_view(["POST"])
@decorators.permission_classes([JWTAuthenticatedPermission])
@decorators.authentication_classes([SessionAuthentication, JWTAuthentication])
def predict(request):
    # Guard before any ORM query. This prevents the production TypeError where
    # a missing cross-subdomain session reached BrokerAccount.user=AnonymousUser.
    if not request.user or not request.user.is_authenticated:
        return response.Response({"detail":"Authentication credentials are required for AI analysis.","code":"NOT_AUTHENTICATED"}, status=status.HTTP_401_UNAUTHORIZED)
    symbol = _discover_symbol(request)
    if not symbol: return response.Response({"detail":"No active broker market is available. Connect a broker and synchronize markets first.","code":"NO_ACTIVE_MARKET"},status=status.HTTP_409_CONFLICT)
    account = _connected_account(request.user)
    if not account: return response.Response({"detail":"Connect a broker before requesting AI analysis.","code":"NO_CONNECTED_BROKER"},status=status.HTTP_409_CONFLICT)
    timeframe = str(request.data.get("timeframe") or "M1").upper()
    try:
        raw_context = _persisted_market_context(symbol, timeframe)
        context_source = raw_context.get("market_data", {}).get("source", "persisted_broker_tick") if raw_context else "live_broker_tick"
        if raw_context is None: raw_context = _broker_market_context(account, symbol)
        ctx = validate_feature_context(raw_context)
        result = AIEngine().analyze(symbol, timeframe, ctx)
        return response.Response({"symbol":symbol,"timeframe":timeframe,"broker":account.broker.name,"account_id":account.account_id,"market_context_source":context_source,"prediction":PredictionSerializer(result["prediction"]).data,"recommendation":AIRecommendationSerializer(result["recommendation"]).data,"regime":MarketRegimeSerializer(result["regime"]).data,"explainability":result["explainability"]})
    except (ValueError, TypeError) as exc: return response.Response({"detail":str(exc),"code":"AI_CONTEXT_INVALID"},status=status.HTTP_400_BAD_REQUEST)
    except asyncio.TimeoutError: return response.Response({"detail":"Connected broker market data timed out; the last known data was not fabricated.","code":"BROKER_MARKET_DATA_TIMEOUT"},status=status.HTTP_504_GATEWAY_TIMEOUT)
    except Exception as exc:
        return response.Response({"detail":"AI analysis failed on the server.","code":"AI_INFERENCE_FAILED","error_id":f"ai-{int(timezone.now().timestamp())}"},status=status.HTTP_503_SERVICE_UNAVAILABLE)


@decorators.api_view(["GET"])
@decorators.permission_classes([JWTAuthenticatedPermission])
@decorators.authentication_classes([SessionAuthentication, JWTAuthentication])
def explain(request):
    symbol = str(request.query_params.get("symbol") or "").strip(); timeframe = str(request.query_params.get("timeframe") or "M1").upper()
    if not symbol: return response.Response({"detail":"symbol is required"},status=status.HTTP_400_BAD_REQUEST)
    features = FeatureStoreService().latest(symbol,timeframe)
    if not features: return response.Response({"detail":"No AI feature vector is available for this market yet."},status=status.HTTP_404_NOT_FOUND)
    return response.Response(ExplainabilityService().explain(features))
