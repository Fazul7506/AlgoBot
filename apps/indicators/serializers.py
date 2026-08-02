from rest_framework import serializers
from .models import Indicator, IndicatorValue, TrendAnalysis, SupportResistanceLevel, PatternDetection
class IndicatorSerializer(serializers.ModelSerializer):
    class Meta: model=Indicator; fields='__all__'
class IndicatorValueSerializer(serializers.ModelSerializer):
    indicator_name=serializers.CharField(source='indicator.name', read_only=True)
    class Meta: model=IndicatorValue; fields='__all__'
class TrendAnalysisSerializer(serializers.ModelSerializer):
    class Meta: model=TrendAnalysis; fields='__all__'
class SupportResistanceLevelSerializer(serializers.ModelSerializer):
    class Meta: model=SupportResistanceLevel; fields='__all__'
class PatternDetectionSerializer(serializers.ModelSerializer):
    class Meta: model=PatternDetection; fields='__all__'
