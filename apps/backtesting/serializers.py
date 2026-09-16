from django.utils import timezone
from rest_framework import serializers

from .models import Backtest, BacktestTrade, BacktestStatistics


class BacktestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Backtest
        fields = '__all__'
        read_only_fields = ('user', 'status', 'result_snapshot', 'result_version')

    def validate(self, attrs):
        if self.instance:
            immutable = {'strategy', 'symbol', 'timeframe', 'mode', 'parameters'}
            changed = immutable.intersection(attrs)
            if changed:
                raise serializers.ValidationError({
                    'detail': 'Only start_date and end_date can be edited after a backtest is created.',
                    'immutable_fields': sorted(changed),
                })
        start = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        if not start or not end:
            raise serializers.ValidationError('Both start_date and end_date are required.')
        if timezone.is_naive(start):
            start = timezone.make_aware(start)
        if timezone.is_naive(end):
            end = timezone.make_aware(end)
        if end <= start:
            raise serializers.ValidationError('end_date must be later than start_date.')
        attrs['start_date'] = start
        attrs['end_date'] = end
        return attrs


class BacktestTradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = BacktestTrade
        fields = '__all__'


class BacktestStatisticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BacktestStatistics
        fields = '__all__'
