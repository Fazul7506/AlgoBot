from rest_framework import serializers
from .models import Strategy,StrategyConfiguration,StrategyExecution,StrategyPerformance,StrategySignal
class StrategySerializer(serializers.ModelSerializer):
    class Meta: model=Strategy; fields='__all__'; read_only_fields=['created_at','updated_at']
class StrategyConfigurationSerializer(serializers.ModelSerializer):
    class Meta: model=StrategyConfiguration; fields='__all__'; read_only_fields=['created_at','updated_at']
class StrategyExecutionSerializer(serializers.ModelSerializer):
    class Meta: model=StrategyExecution; fields='__all__'
class StrategyPerformanceSerializer(serializers.ModelSerializer):
    class Meta: model=StrategyPerformance; fields='__all__'
class StrategySignalSerializer(serializers.ModelSerializer):
    class Meta: model=StrategySignal; fields='__all__'
