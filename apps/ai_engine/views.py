from rest_framework import viewsets, permissions, decorators, response
from .models import AIModel, Prediction, FeatureVector, TrainingJob, AIRecommendation, MarketRegime, AnomalyEvent
from .serializers import *
from .services import AIEngine, TrainingService, ExplainabilityService, FeatureStoreService
from .validators import validate_feature_context
class AIModelViewSet(viewsets.ModelViewSet): queryset=AIModel.objects.all(); serializer_class=AIModelSerializer; permission_classes=[permissions.IsAuthenticatedOrReadOnly]
class PredictionViewSet(viewsets.ReadOnlyModelViewSet): queryset=Prediction.objects.all(); serializer_class=PredictionSerializer
class RecommendationViewSet(viewsets.ReadOnlyModelViewSet): queryset=AIRecommendation.objects.all(); serializer_class=AIRecommendationSerializer
class MarketRegimeViewSet(viewsets.ReadOnlyModelViewSet): queryset=MarketRegime.objects.all(); serializer_class=MarketRegimeSerializer
class FeatureVectorViewSet(viewsets.ReadOnlyModelViewSet): queryset=FeatureVector.objects.all(); serializer_class=FeatureVectorSerializer
class AnomalyViewSet(viewsets.ReadOnlyModelViewSet): queryset=AnomalyEvent.objects.all(); serializer_class=AnomalyEventSerializer
class TrainingJobViewSet(viewsets.ModelViewSet): queryset=TrainingJob.objects.all(); serializer_class=TrainingJobSerializer
@decorators.api_view(['POST'])
def train(request):
    return response.Response(TrainingJobSerializer(TrainingService().train(mode=request.data.get('mode','manual'))).data)
@decorators.api_view(['POST'])
def predict(request):
    ctx=validate_feature_context(request.data.get('context',{})); result=AIEngine().analyze(request.data.get('symbol','R_100'), request.data.get('timeframe','M1'), ctx)
    return response.Response({'prediction':PredictionSerializer(result['prediction']).data,'recommendation':AIRecommendationSerializer(result['recommendation']).data,'regime':MarketRegimeSerializer(result['regime']).data,'explainability':result['explainability']})
@decorators.api_view(['GET'])
def explain(request):
    features=FeatureStoreService().latest(request.query_params.get('symbol','R_100'), request.query_params.get('timeframe','M1'))
    return response.Response(ExplainabilityService().explain(features))
