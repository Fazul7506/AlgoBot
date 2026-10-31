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
    bid = serializers.SerializerMethodField()
    ask = serializers.SerializerMethodField()
    spread = serializers.SerializerMethodField()
    bid_ask_available = serializers.SerializerMethodField()

    class Meta:
        model = Tick
        fields = ['id', 'symbol', 'bid', 'ask', 'quote', 'spread', 'bid_ask_source', 'bid_ask_available', 'epoch', 'volume', 'received_at', 'created_at']

    def get_bid(self, obj):
        return str(obj.bid) if obj.bid_ask_source in {'broker', 'partial'} and obj.bid is not None else None

    def get_ask(self, obj):
        return str(obj.ask) if obj.bid_ask_source in {'broker', 'partial'} and obj.ask is not None else None

    def get_spread(self, obj):
        return str(obj.spread) if obj.bid_ask_source == 'broker' and obj.bid is not None and obj.ask is not None else None

    def get_bid_ask_available(self, obj):
        return obj.bid_ask_source == 'broker' and obj.bid is not None and obj.ask is not None


class CandleSerializer(serializers.ModelSerializer):
    symbol = serializers.SlugRelatedField(slug_field='symbol', read_only=True)
    class Meta: model = Candle; fields = '__all__'


class MarketSnapshotSerializer(serializers.ModelSerializer):
    symbol = serializers.SlugRelatedField(slug_field='symbol', read_only=True)
    bid = serializers.SerializerMethodField()
    ask = serializers.SerializerMethodField()
    spread = serializers.SerializerMethodField()
    bid_ask_available = serializers.SerializerMethodField()

    class Meta:
        model = MarketSnapshot
        fields = ['id', 'symbol', 'last_price', 'bid', 'ask', 'spread', 'bid_ask_source', 'bid_ask_available', 'high', 'low', 'change', 'change_percent', 'volume', 'timestamp']

    def get_bid(self, obj):
        return str(obj.bid) if obj.bid_ask_source in {'broker', 'partial'} and obj.bid is not None else None

    def get_ask(self, obj):
        return str(obj.ask) if obj.bid_ask_source in {'broker', 'partial'} and obj.ask is not None else None

    def get_spread(self, obj):
        return str(obj.spread) if obj.bid_ask_source == 'broker' and obj.bid is not None and obj.ask is not None else None

    def get_bid_ask_available(self, obj):
        return obj.bid_ask_source == 'broker' and obj.bid is not None and obj.ask is not None


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta: model = Subscription; fields = '__all__'


class MarketStatisticsSerializer(serializers.ModelSerializer):
    symbol = serializers.SlugRelatedField(slug_field='symbol', read_only=True)
    average_spread = serializers.SerializerMethodField()

    class Meta:
        model = MarketStatistics
        fields = '__all__'

    def get_average_spread(self, obj):
        return str(obj.average_spread) if obj.spread_sample_count > 0 else None
