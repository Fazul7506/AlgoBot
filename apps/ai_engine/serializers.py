from rest_framework import serializers

from .models import (
    AIModel,
    AIRecommendation,
    AnomalyEvent,
    FeatureVector,
    MarketRegime,
    ModelVersion,
    Prediction,
    TrainingJob,
)


class AIModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIModel
        fields = "__all__"


class ModelVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelVersion
        fields = "__all__"


class PredictionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prediction
        exclude = ("user",)
        read_only_fields = tuple(field.name for field in Prediction._meta.fields if field.name != "user")


class FeatureVectorSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeatureVector
        fields = "__all__"


class TrainingJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingJob
        exclude = ("user",)
        read_only_fields = tuple(field.name for field in TrainingJob._meta.fields if field.name != "user")


class AIRecommendationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIRecommendation
        exclude = ("user",)
        read_only_fields = tuple(field.name for field in AIRecommendation._meta.fields if field.name != "user")


class MarketRegimeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketRegime
        exclude = ("user",)
        read_only_fields = tuple(field.name for field in MarketRegime._meta.fields if field.name != "user")


class AnomalyEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnomalyEvent
        exclude = ("user",)
        read_only_fields = tuple(field.name for field in AnomalyEvent._meta.fields if field.name != "user")
