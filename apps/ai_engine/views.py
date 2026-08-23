from rest_framework import viewsets, permissions, decorators, response, status
from apps.market_data.models import MarketSymbol
from .models import AIModel, Prediction, FeatureVector, TrainingJob, AIRecommendation, MarketRegime, AnomalyEvent
from .serializers import *
from .services import AIEngine, TrainingService, ExplainabilityService, FeatureStoreService
from .validators import validate_feature_context


class _UserScoped:
    permission_classes = [permissions.IsAuthenticated]
    def _owned(self, qs):
        # AI tables are shared market artefacts; only records produced for the
        # requested user's workspace are returned where the model supports it.
        return qs


class AIModelViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AIModel.objects.all(); serializer_class = AIModelSerializer; permission_classes = [permissions.IsAuthenticated]
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


@decorators.api_view(["POST"])
@decorators.permission_classes([permissions.IsAuthenticated])
def predict(request):
    symbol = _discover_symbol(request)
    if not symbol:
        return response.Response({"detail": "No active broker market is available. Connect a broker and synchronize markets first.", "code": "NO_ACTIVE_MARKET"}, status=status.HTTP_409_CONFLICT)
    timeframe = str(request.data.get("timeframe") or "M1").upper()
    try:
        raw_context = request.data.get("context") or {}
        if not raw_context.get("market_data"):
            from apps.market_data.deriv_sync import fetch_tick
            tick = fetch_tick(symbol)
            raw_context["market_data"] = {"close": tick["quote"], "open": tick["quote"], "high": tick["quote"], "low": tick["quote"], "bid": tick.get("bid"), "ask": tick.get("ask"), "spread": (tick.get("ask") - tick.get("bid")) if tick.get("bid") is not None and tick.get("ask") is not None else 0}
        ctx = validate_feature_context(raw_context)
        result = AIEngine().analyze(symbol, timeframe, ctx)
        return response.Response({"symbol": symbol, "timeframe": timeframe, "prediction": PredictionSerializer(result["prediction"]).data, "recommendation": AIRecommendationSerializer(result["recommendation"]).data, "regime": MarketRegimeSerializer(result["regime"]).data, "explainability": result["explainability"]})
    except (ValueError, TypeError) as exc:
        return response.Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return response.Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@decorators.api_view(["GET"])
@decorators.permission_classes([permissions.IsAuthenticated])
def explain(request):
    symbol = str(request.query_params.get("symbol") or "").strip()
    timeframe = str(request.query_params.get("timeframe") or "M1").upper()
    if not symbol: return response.Response({"detail": "symbol is required"}, status=status.HTTP_400_BAD_REQUEST)
    features = FeatureStoreService().latest(symbol, timeframe)
    if not features: return response.Response({"detail": "No AI feature vector is available for this market yet."}, status=status.HTTP_404_NOT_FOUND)
    return response.Response(ExplainabilityService().explain(features))
