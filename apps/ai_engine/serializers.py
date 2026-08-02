from rest_framework import serializers
from .models import AIModel, ModelVersion, Prediction, FeatureVector, TrainingJob, AIRecommendation, MarketRegime, AnomalyEvent
class AIModelSerializer(serializers.ModelSerializer):
    class Meta: model=AIModel; fields='__all__'
class ModelVersionSerializer(serializers.ModelSerializer):
    class Meta: model=ModelVersion; fields='__all__'
class PredictionSerializer(serializers.ModelSerializer):
    class Meta: model=Prediction; fields='__all__'
class FeatureVectorSerializer(serializers.ModelSerializer):
    class Meta: model=FeatureVector; fields='__all__'
class TrainingJobSerializer(serializers.ModelSerializer):
    class Meta: model=TrainingJob; fields='__all__'
class AIRecommendationSerializer(serializers.ModelSerializer):
    class Meta: model=AIRecommendation; fields='__all__'
class MarketRegimeSerializer(serializers.ModelSerializer):
    class Meta: model=MarketRegime; fields='__all__'
class AnomalyEventSerializer(serializers.ModelSerializer):
    class Meta: model=AnomalyEvent; fields='__all__'
