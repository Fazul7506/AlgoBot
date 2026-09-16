from django.utils import timezone
from rest_framework import serializers

from .models import Backtest, BacktestTrade, BacktestStatistics
from apps.market_data.constants import TIMEFRAMES


TIMEFRAME_ALIASES = {
    'TICK': 'tick',
    'M1': '1m',
    'M2': '2m',
    'M5': '5m',
    'M10': '10m',
    'M15': '15m',
    'M30': '30m',
    'H1': '1h',
    'H4': '4h',
    'D1': '1d',
}


def canonical_timeframe(value):
    raw = str(value or '').strip()
    if not raw:
        return ''
    lower = raw.lower()
    if lower in TIMEFRAMES:
        return lower
    return TIMEFRAME_ALIASES.get(raw.upper(), lower)


class BacktestSerializer(serializers.ModelSerializer):
    # Research handoff identifiers are write-only routing hints. The persisted
    # Backtest keeps the canonical strategy name for historical reproducibility.
    strategy_id = serializers.IntegerField(required=False, write_only=True)
    strategy_slug = serializers.CharField(required=False, write_only=True, allow_blank=True)

    class Meta:
        model = Backtest
        fields = '__all__'
        read_only_fields = ('user', 'status', 'result_snapshot', 'result_version')

    def to_internal_value(self, data):
        normalized = data.copy() if hasattr(data, 'copy') else dict(data)
        if 'timeframe' in normalized:
            normalized['timeframe'] = canonical_timeframe(normalized.get('timeframe'))
        return super().to_internal_value(normalized)

    def validate(self, attrs):
        attrs.pop('strategy_id', None)
        attrs.pop('strategy_slug', None)

        if 'timeframe' in attrs:
            timeframe = canonical_timeframe(attrs.get('timeframe'))
            if timeframe not in TIMEFRAMES:
                raise serializers.ValidationError({
                    'timeframe': f'The selected timeframe is not supported by AlgoBot. Supported values: {", ".join(TIMEFRAMES.keys())}.'
                })
            attrs['timeframe'] = timeframe

        if self.instance:
            if self.instance.status != 'pending':
                raise serializers.ValidationError({'status': 'Only pending backtests can be edited.'})
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
        if not self.instance and end > timezone.now():
            raise serializers.ValidationError({'end_date': 'Backtests are historical only; end_date cannot be in the future.'})
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
