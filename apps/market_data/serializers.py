from rest_framework import serializers
from .models import MarketSymbol, Tick, Candle, MarketSnapshot, Subscription, MarketStatistics
from apps.brokers.models import Broker


class MarketSymbolSerializer(serializers.ModelSerializer):
    broker_avatar_url = serializers.SerializerMethodField()
    broker_name = serializers.SerializerMethodField()
    broker_type = serializers.SerializerMethodField()

    class Meta:
        model = MarketSymbol
        fields = [
            'id', 'broker', 'broker_name', 'broker_type', 'broker_avatar_url', 'symbol',
            'display_name', 'market', 'sub_market', 'pip_size', 'tick_size', 'currency',
            'is_active', 'is_tradable', 'created_at',
        ]
        read_only_fields = ['broker_name', 'broker_type', 'broker_avatar_url']

    def _broker(self, obj):
        # MarketSymbol historically stores the provider identifier as a string.
        # Resolve that identifier to the canonical Broker record without changing
        # the existing database schema or market identifiers.
        value = str(obj.broker or '').strip()
        return Broker.objects.filter(broker_type__iexact=value).order_by('id').first() or Broker.objects.filter(name__iexact=value).order_by('id').first()

    def get_broker_avatar_url(self, obj):
        broker = self._broker(obj)
        return str((broker.metadata or {}).get('avatar_url') or '') if broker else ''

    def get_broker_name(self, obj):
        broker = self._broker(obj)
        return broker.name if broker else str(obj.broker or '')

    def get_broker_type(self, obj):
        broker = self._broker(obj)
        return broker.broker_type if broker else str(obj.broker or '')


class TickSerializer(serializers.ModelSerializer):
    symbol = serializers.SlugRelatedField(slug_field='symbol', read_only=True)
    class Meta: model = Tick; fields = '__all__'


class CandleSerializer(serializers.ModelSerializer):
    symbol = serializers.SlugRelatedField(slug_field='symbol', read_only=True)
    class Meta: model = Candle; fields = '__all__'


class MarketSnapshotSerializer(serializers.ModelSerializer):
    symbol = serializers.SlugRelatedField(slug_field='symbol', read_only=True)
    class Meta: model = MarketSnapshot; fields = '__all__'


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta: model = Subscription; fields = '__all__'


class MarketStatisticsSerializer(serializers.ModelSerializer):
    symbol = serializers.SlugRelatedField(slug_field='symbol', read_only=True)
    class Meta: model = MarketStatistics; fields = '__all__'
