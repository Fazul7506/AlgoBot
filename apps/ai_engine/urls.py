from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AIModelViewSet,
    AnomalyViewSet,
    FeatureVectorViewSet,
    MarketRegimeViewSet,
    ModelVersionViewSet,
    PredictionViewSet,
    RecommendationViewSet,
    TrainingJobViewSet,
    explain,
    model_governance,
    predict,
    train,
)

router = DefaultRouter()
router.register(r"ai/models", AIModelViewSet, basename="ai-models")
router.register(r"ai/predictions", PredictionViewSet, basename="ai-predictions")
router.register(r"ai/recommendations", RecommendationViewSet, basename="ai-recommendations")
router.register(r"ai/regime", MarketRegimeViewSet, basename="ai-regime")
router.register(r"ai/features", FeatureVectorViewSet, basename="ai-features")
router.register(r"ai/anomalies", AnomalyViewSet, basename="ai-anomalies")
router.register(r"ai/training-jobs", TrainingJobViewSet, basename="ai-training-jobs")

urlpatterns = [
    path("", include(router.urls)),
    path("ai/governance/", model_governance, name="ai-governance"),
    path("ai/train/", train, name="ai-train"),
    path("ai/predict/", predict, name="ai-predict"),
    path("ai/explain/", explain, name="ai-explain"),
]
