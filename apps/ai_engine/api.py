"""Stable compatibility exports for the AI HTTP API."""

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

__all__ = [
    "AIModelViewSet",
    "AnomalyViewSet",
    "FeatureVectorViewSet",
    "MarketRegimeViewSet",
    "ModelVersionViewSet",
    "PredictionViewSet",
    "RecommendationViewSet",
    "TrainingJobViewSet",
    "explain",
    "model_governance",
    "predict",
    "train",
]
