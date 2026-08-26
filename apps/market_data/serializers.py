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
        # MarketSymbol stores the provider identifier as a string. Cache the
        # small broker catalogue once per serializer/request so a catalogue of
        # hundreds of instruments never performs one or more DB queries per row.
        cache = self.context.setdefault('_broker_catalogue_cache', {})
        value = str(obj.broker or '').strip().lower()
        if value in cache:
            return cache[value]
        broker = (
            Broker.objects.filter(broker_type__iexact=value).order_by('id').first()
            or Broker.objects.filter(name__iexact=value).order_by('id').first()
        )
        cache[value] = broker
        return broker

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
