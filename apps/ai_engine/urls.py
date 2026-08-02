from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AIModelViewSet, PredictionViewSet, RecommendationViewSet, MarketRegimeViewSet, FeatureVectorViewSet, AnomalyViewSet, TrainingJobViewSet, train, predict, explain
router=DefaultRouter()
router.register(r'ai/models', AIModelViewSet, basename='ai-models')
router.register(r'ai/predictions', PredictionViewSet, basename='ai-predictions')
router.register(r'ai/recommendations', RecommendationViewSet, basename='ai-recommendations')
router.register(r'ai/regime', MarketRegimeViewSet, basename='ai-regime')
router.register(r'ai/features', FeatureVectorViewSet, basename='ai-features')
router.register(r'ai/anomalies', AnomalyViewSet, basename='ai-anomalies')
router.register(r'ai/training-jobs', TrainingJobViewSet, basename='ai-training-jobs')
urlpatterns=[path('', include(router.urls)), path('ai/train/', train), path('ai/predict/', predict), path('ai/explain/', explain)]
