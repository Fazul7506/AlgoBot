from rest_framework import serializers
from trading.models.market import MarketSymbol, PriceHistory, MarketSnapshot, TickData, DataStreamSession


class MarketSymbolSerializer(serializers.ModelSerializer):
    """Serializer for market symbols"""
    
    class Meta:
        model = MarketSymbol
        fields = [
            'id', 'symbol', 'display_name', 'market_type', 'description',
            'min_stake', 'max_stake', 'pip_size', 'is_active', 'is_tradeable',
            'supported_timeframes', 'market_open', 'market_close', 'timezone',
            'avg_spread', 'trading_volume_24h', 'last_tick_time'
        ]
        read_only_fields = ['id', 'last_tick_time']


class MarketSnapshotSerializer(serializers.ModelSerializer):
    """Serializer for market snapshots"""
    
    symbol_name = serializers.CharField(source='symbol.symbol', read_only=True)
    display_name = serializers.CharField(source='symbol.display_name', read_only=True)
    
    class Meta:
        model = MarketSnapshot
        fields = [
            'id', 'symbol_name', 'display_name', 'current_bid', 'current_ask',
            'last_price', 'high_24h', 'low_24h', 'change_24h', 'change_pct_24h',
            'bid_ask_spread', 'spread_pct', 'volume_24h', 'updated_at'
        ]
        read_only_fields = fields


class PriceHistorySerializer(serializers.ModelSerializer):
    """Serializer for price history/candles"""
    
    symbol_name = serializers.CharField(source='symbol.symbol', read_only=True)
    
    class Meta:
        model = PriceHistory
        fields = [
            'id', 'symbol_name', 'timeframe', 'open', 'high', 'low', 'close',
            'volume', 'tick_count', 'candle_time', 'candle_end_time'
        ]
        read_only_fields = ['id', 'created_at']


class ChartDataSerializer(serializers.Serializer):
    """Serializer for chart data response"""
    
    symbol = serializers.CharField()
    timeframe = serializers.CharField()
    candles = PriceHistorySerializer(many=True)
    latest_snapshot = serializers.SerializerMethodField()
    
    def get_latest_snapshot(self, obj):
        snapshot = obj.get('snapshot')
        if snapshot:
            return MarketSnapshotSerializer(snapshot).data
        return None


class TickDataSerializer(serializers.ModelSerializer):
    """Serializer for tick data"""
    
    symbol_name = serializers.CharField(source='symbol.symbol', read_only=True)
    
    class Meta:
        model = TickData
        fields = [
            'id', 'symbol_name', 'bid', 'ask', 'epoch', 'spread', 'tick_number'
        ]
        read_only_fields = fields


class DataStreamSessionSerializer(serializers.ModelSerializer):
    """Serializer for streaming sessions"""
    
    symbol_name = serializers.CharField(source='symbol.symbol', read_only=True)
    uptime_minutes = serializers.SerializerMethodField()
    
    class Meta:
        model = DataStreamSession
        fields = [
            'id', 'session_id', 'symbol_name', 'status', 'connected_at',
            'disconnected_at', 'ticks_received', 'bytes_received', 'last_tick_at',
            'error_count', 'last_error', 'uptime_minutes'
        ]
        read_only_fields = fields
    
    def get_uptime_minutes(self, obj):
        if obj.connected_at and obj.disconnected_at is None:
            return int((obj.updated_at - obj.connected_at).total_seconds() / 60)
        return 0


class MarketDataStatsSerializer(serializers.Serializer):
    """Serializer for market data statistics"""
    
    total_symbols = serializers.IntegerField()
    active_symbols = serializers.IntegerField()
    total_candles = serializers.IntegerField()
    total_ticks = serializers.IntegerField()
    active_streams = serializers.IntegerField()
    cache_hits = serializers.IntegerField(default=0)
    cache_size_mb = serializers.FloatField(default=0.0)


class MarketRegimeSerializer(serializers.Serializer):
    """Serializer for market regime dashboard output"""
    symbol = serializers.CharField()
    timeframe = serializers.CharField()
    market_regime = serializers.CharField()
    recommended_strategy = serializers.CharField()
    trend_direction = serializers.CharField()
    volatility = serializers.FloatField(allow_null=True)
    range_pct = serializers.FloatField(allow_null=True)
    trend_pct = serializers.FloatField(allow_null=True)
    short_ma = serializers.FloatField(allow_null=True)
    mid_ma = serializers.FloatField(allow_null=True)
    long_ma = serializers.FloatField(allow_null=True)
    structure_insight = serializers.DictField()
