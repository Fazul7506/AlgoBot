from rest_framework import serializers
from trading.models.core import BacktestResult


class BacktestResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = BacktestResult
        fields = [
            'id', 'strategy', 'symbol', 'timeframe', 'start_date', 'end_date',
            'initial_balance', 'total_trades', 'wins', 'losses', 'win_rate',
            'expectancy', 'sharpe_ratio', 'sortino_ratio', 'max_drawdown',
            'max_drawdown_pct', 'profit_factor', 'total_profit', 'total_profit_pct',
            'final_balance', 'created_at'
        ]
