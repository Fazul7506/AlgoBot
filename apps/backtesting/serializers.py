from rest_framework import serializers
from .models import Backtest, BacktestTrade, BacktestStatistics
class BacktestSerializer(serializers.ModelSerializer):
    class Meta: model=Backtest; fields='__all__'; read_only_fields=('user','status','result_snapshot','result_version')
class BacktestTradeSerializer(serializers.ModelSerializer):
    class Meta: model=BacktestTrade; fields='__all__'
class BacktestStatisticsSerializer(serializers.ModelSerializer):
    class Meta: model=BacktestStatistics; fields='__all__'
