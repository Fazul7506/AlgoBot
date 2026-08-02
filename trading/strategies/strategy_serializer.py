from rest_framework import serializers
from trading.models.core import Strategy


class StrategySerializer(serializers.ModelSerializer):
    class Meta:
        model = Strategy
        fields = [
            'id', 'name', 'strategy_type', 'description', 'config',
            'is_active', 'is_paper_only', 'version', 'total_trades',
            'winning_trades', 'losing_trades', 'win_rate', 'total_pnl',
            'created_at', 'updated_at'
        ]
