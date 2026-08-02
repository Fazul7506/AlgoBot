from rest_framework import serializers
from .models import MarketSymbol, Tick, Candle, MarketSnapshot, Subscription, MarketStatistics

class MarketSymbolSerializer(serializers.ModelSerializer):
    class Meta: model = MarketSymbol; fields = "__all__"
class TickSerializer(serializers.ModelSerializer):
    symbol = serializers.SlugRelatedField(slug_field="symbol", read_only=True)
    class Meta: model = Tick; fields = "__all__"
class CandleSerializer(serializers.ModelSerializer):
    symbol = serializers.SlugRelatedField(slug_field="symbol", read_only=True)
    class Meta: model = Candle; fields = "__all__"
class MarketSnapshotSerializer(serializers.ModelSerializer):
    symbol = serializers.SlugRelatedField(slug_field="symbol", read_only=True)
    class Meta: model = MarketSnapshot; fields = "__all__"
class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta: model = Subscription; fields = "__all__"
class MarketStatisticsSerializer(serializers.ModelSerializer):
    symbol = serializers.SlugRelatedField(slug_field="symbol", read_only=True)
    class Meta: model = MarketStatistics; fields = "__all__"
