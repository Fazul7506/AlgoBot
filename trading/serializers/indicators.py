from rest_framework import serializers
from trading.models.market import MarketSymbol
from trading.models.indicators import IndicatorValue, TechnicalSignal, IndicatorProfile, IndicatorAlert


class IndicatorValueSerializer(serializers.ModelSerializer):
    """Serializer for indicator values"""
    
    symbol_name = serializers.CharField(source='symbol.symbol', read_only=True)
    
    class Meta:
        model = IndicatorValue
        fields = [
            'id', 'symbol_name', 'indicator_type', 'timeframe', 'period',
            'value', 'candle_time', 'calculated_at'
        ]
        read_only_fields = ['id', 'calculated_at']


class TechnicalSignalSerializer(serializers.ModelSerializer):
    """Serializer for technical signals"""
    
    symbol_name = serializers.CharField(source='symbol.symbol', read_only=True)
    confidence_pct = serializers.SerializerMethodField()
    strength_pct = serializers.SerializerMethodField()
    
    class Meta:
        model = TechnicalSignal
        fields = [
            'id', 'symbol_name', 'timeframe', 'signal_type', 'signal_source',
            'confidence', 'confidence_pct', 'strength', 'strength_pct',
            'contributing_indicators', 'candle_time', 'was_executed', 'created_at'
        ]
        read_only_fields = fields
    
    def get_confidence_pct(self, obj):
        return f"{obj.confidence * 100:.1f}%"
    
    def get_strength_pct(self, obj):
        return f"{obj.strength * 100:.1f}%"


class IndicatorProfileSerializer(serializers.ModelSerializer):
    """Serializer for indicator profiles"""
    
    username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = IndicatorProfile
        fields = [
            'id', 'username', 'profile_type',
            'sma_periods', 'ema_periods', 'wma_periods', 'hma_period',
            'rsi_period', 'rsi_overbought', 'rsi_oversold',
            'macd_fast', 'macd_slow', 'macd_signal',
            'stochastic_period', 'stochastic_k_period', 'stochastic_d_period',
            'atr_period', 'bb_period', 'bb_std_dev',
            'adx_period', 'adx_threshold',
            'require_multiple_indicators', 'min_confidence',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'username', 'created_at', 'updated_at']


class IndicatorAlertSerializer(serializers.ModelSerializer):
    """Serializer for indicator alerts"""
    
    username = serializers.CharField(source='user.username', read_only=True)
    symbol = serializers.PrimaryKeyRelatedField(queryset=MarketSymbol.objects.all(), write_only=True)
    symbol_name = serializers.CharField(source='symbol.symbol', read_only=True)
    
    class Meta:
        model = IndicatorAlert
        fields = [
            'id', 'username', 'symbol', 'symbol_name', 'alert_type', 'indicator_type',
            'condition_value', 'comparison', 'is_active', 'times_triggered',
            'last_triggered', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'username', 'times_triggered', 'last_triggered', 'created_at', 'updated_at']


class IndicatorDashboardSerializer(serializers.Serializer):
    """Serializer for indicator dashboard data"""
    
    symbol = serializers.CharField()
    timeframe = serializers.CharField()
    timestamp = serializers.DateTimeField()
    
    # Trend indicators
    sma_20 = serializers.FloatField(allow_null=True)
    sma_50 = serializers.FloatField(allow_null=True)
    sma_200 = serializers.FloatField(allow_null=True)
    ema_12 = serializers.FloatField(allow_null=True)
    ema_26 = serializers.FloatField(allow_null=True)
    wma_20 = serializers.FloatField(allow_null=True)
    hma = serializers.FloatField(allow_null=True)
    
    # Momentum indicators
    rsi = serializers.FloatField(allow_null=True)
    macd = serializers.FloatField(allow_null=True)
    macd_signal = serializers.FloatField(allow_null=True)
    macd_histogram = serializers.FloatField(allow_null=True)
    stochastic_k = serializers.FloatField(allow_null=True)
    stochastic_d = serializers.FloatField(allow_null=True)
    
    # Volatility indicators
    atr = serializers.FloatField(allow_null=True)
    bb_upper = serializers.FloatField(allow_null=True)
    bb_middle = serializers.FloatField(allow_null=True)
    bb_lower = serializers.FloatField(allow_null=True)
    
    # Trend strength
    adx = serializers.FloatField(allow_null=True)
    di_plus = serializers.FloatField(allow_null=True)
    di_minus = serializers.FloatField(allow_null=True)
    
    # Signal
    signal_type = serializers.CharField(allow_null=True)
    signal_strength = serializers.FloatField(allow_null=True)


class IndicatorComparisonSerializer(serializers.Serializer):
    """Serializer for comparing indicators across symbols"""
    
    symbol = serializers.CharField()
    rsi = serializers.FloatField(allow_null=True)
    macd = serializers.FloatField(allow_null=True)
    atr = serializers.FloatField(allow_null=True)
    adx = serializers.FloatField(allow_null=True)
    trend = serializers.CharField()
    signal = serializers.CharField(allow_null=True)


class IndicatorHistorySerializer(serializers.Serializer):
    """Serializer for indicator history"""
    
    timestamp = serializers.DateTimeField()
    value = serializers.FloatField()
    signal = serializers.CharField(allow_null=True)


class SignalStatisticsSerializer(serializers.Serializer):
    """Serializer for signal statistics"""
    
    total_signals = serializers.IntegerField()
    bullish_signals = serializers.IntegerField()
    bearish_signals = serializers.IntegerField()
    bullish_percentage = serializers.FloatField()
    avg_confidence = serializers.FloatField()
    avg_strength = serializers.FloatField()
    win_rate = serializers.FloatField(allow_null=True)
    avg_return = serializers.FloatField(allow_null=True)
