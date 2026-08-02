from django.db import models
from django.utils import timezone
from trading.models.market import MarketSymbol
from trading.models.core import Trade, Strategy


class IndicatorValue(models.Model):
    """Store calculated indicator values for technical analysis"""
    
    INDICATOR_TYPES = [
        ('SMA', 'Simple Moving Average'),
        ('EMA', 'Exponential Moving Average'),
        ('WMA', 'Weighted Moving Average'),
        ('HMA', 'Hull Moving Average'),
        ('RSI', 'Relative Strength Index'),
        ('MACD', 'MACD'),
        ('MACD_Signal', 'MACD Signal Line'),
        ('MACD_Histogram', 'MACD Histogram'),
        ('Stochastic_K', 'Stochastic %K'),
        ('Stochastic_D', 'Stochastic %D'),
        ('ATR', 'Average True Range'),
        ('BB_Upper', 'Bollinger Bands Upper'),
        ('BB_Middle', 'Bollinger Bands Middle'),
        ('BB_Lower', 'Bollinger Bands Lower'),
        ('BB_Width', 'Bollinger Bands Width'),
        ('ADX', 'Average Directional Index'),
        ('DI_Plus', 'Directional Indicator Plus'),
        ('DI_Minus', 'Directional Indicator Minus'),
    ]
    
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name='indicator_values')
    indicator_type = models.CharField(max_length=20, choices=INDICATOR_TYPES)
    timeframe = models.CharField(max_length=10)  # M1, M5, H1, D1, etc.
    
    # Indicator parameters
    period = models.IntegerField(null=True, blank=True)  # Period for calculation
    
    # Value
    value = models.FloatField()
    
    # Timestamp
    candle_time = models.DateTimeField()  # Time of the candle this indicator is for
    calculated_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-candle_time']
        indexes = [
            models.Index(fields=['symbol', 'indicator_type', 'timeframe', '-candle_time']),
            models.Index(fields=['candle_time']),
        ]
        unique_together = [['symbol', 'indicator_type', 'timeframe', 'period', 'candle_time']]
    
    def __str__(self):
        return f"{self.symbol.symbol} {self.indicator_type} {self.timeframe} = {self.value:.4f}"


class TechnicalSignal(models.Model):
    """Trading signals generated from technical indicators"""
    
    SIGNAL_TYPE_CHOICES = [
        ('BULLISH', 'Bullish Signal'),
        ('BEARISH', 'Bearish Signal'),
        ('NEUTRAL', 'Neutral Signal'),
        ('STRONG_BULLISH', 'Strong Bullish'),
        ('STRONG_BEARISH', 'Strong Bearish'),
    ]
    
    SIGNAL_SOURCE_CHOICES = [
        ('SMA_Cross', 'SMA Crossover'),
        ('EMA_Cross', 'EMA Crossover'),
        ('RSI_Overbought', 'RSI Overbought'),
        ('RSI_Oversold', 'RSI Oversold'),
        ('MACD_Cross', 'MACD Crossover'),
        ('Stochastic_Cross', 'Stochastic Crossover'),
        ('BB_Breakout', 'Bollinger Bands Breakout'),
        ('ADX_Trend', 'ADX Trend Confirmation'),
        ('Structure_Break', 'Break of Structure'),
        ('Structure_Retest', 'Change of Character'),
        ('OrderBlock', 'Order Block'),
        ('FairValueGap', 'Fair Value Gap'),
        ('LiquidityPool', 'Liquidity Pool'),
        ('Multi_Indicator', 'Multiple Indicators'),
    ]
    
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name='technical_signals')
    timeframe = models.CharField(max_length=10)
    
    signal_type = models.CharField(max_length=20, choices=SIGNAL_TYPE_CHOICES)
    signal_source = models.CharField(max_length=50, choices=SIGNAL_SOURCE_CHOICES)
    
    # Signal details
    confidence = models.FloatField(default=0.5)  # 0.0 to 1.0
    strength = models.FloatField(default=0.5)  # 0.0 to 1.0 (how strong is the signal)
    
    # Contributing indicators
    contributing_indicators = models.JSONField(default=dict)  # {indicator: value}
    
    # Timing
    candle_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Execution
    was_executed = models.BooleanField(default=False)
    execution_trade = models.ForeignKey(Trade, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-candle_time']
        indexes = [
            models.Index(fields=['symbol', 'timeframe', '-candle_time']),
            models.Index(fields=['signal_type', '-candle_time']),
        ]
    
    def __str__(self):
        return f"{self.symbol.symbol} {self.signal_type} ({self.confidence:.1%}) - {self.candle_time}"


class IndicatorProfile(models.Model):
    """User-customized indicator settings"""
    
    PROFILE_TYPES = [
        ('AGGRESSIVE', 'Aggressive (short-term)'),
        ('BALANCED', 'Balanced'),
        ('CONSERVATIVE', 'Conservative (long-term)'),
        ('CUSTOM', 'Custom'),
    ]
    
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE, related_name='indicator_profile')
    profile_type = models.CharField(max_length=20, choices=PROFILE_TYPES, default='BALANCED')
    
    # Trend indicators
    sma_periods = models.JSONField(default=list)  # [20, 50, 200]
    ema_periods = models.JSONField(default=list)  # [12, 26]
    wma_periods = models.JSONField(default=list)
    hma_period = models.IntegerField(default=9)
    
    # Momentum indicators
    rsi_period = models.IntegerField(default=14)
    rsi_overbought = models.FloatField(default=70.0)
    rsi_oversold = models.FloatField(default=30.0)
    
    macd_fast = models.IntegerField(default=12)
    macd_slow = models.IntegerField(default=26)
    macd_signal = models.IntegerField(default=9)
    
    stochastic_period = models.IntegerField(default=14)
    stochastic_k_period = models.IntegerField(default=3)
    stochastic_d_period = models.IntegerField(default=3)
    
    # Volatility indicators
    atr_period = models.IntegerField(default=14)
    bb_period = models.IntegerField(default=20)
    bb_std_dev = models.FloatField(default=2.0)
    
    # Trend strength
    adx_period = models.IntegerField(default=14)
    adx_threshold = models.FloatField(default=25.0)  # Minimum ADX for trend strength
    
    # Signal generation settings
    require_multiple_indicators = models.BooleanField(default=True)
    min_confidence = models.FloatField(default=0.5)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Indicator Profile"
        verbose_name_plural = "Indicator Profiles"
    
    def __str__(self):
        return f"Indicator Profile - {self.user.username} ({self.profile_type})"


class IndicatorAlert(models.Model):
    """Alert when specific indicator conditions are met"""
    
    ALERT_TYPES = [
        ('CROSSOVER', 'Indicator Crossover'),
        ('OVERBOUGHT', 'Overbought Condition'),
        ('OVERSOLD', 'Oversold Condition'),
        ('THRESHOLD', 'Threshold Breach'),
        ('DIVERGENCE', 'Price/Indicator Divergence'),
    ]
    
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='indicator_alerts')
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name='alerts')
    
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    indicator_type = models.CharField(max_length=20)  # RSI, MACD, etc.
    
    # Alert condition
    condition_value = models.FloatField()  # Threshold value
    comparison = models.CharField(max_length=10, choices=[
        ('>', 'Greater than'),
        ('<', 'Less than'),
        ('>=', 'Greater than or equal'),
        ('<=', 'Less than or equal'),
        ('==', 'Equal to'),
    ])
    
    is_active = models.BooleanField(default=True)
    times_triggered = models.IntegerField(default=0)
    last_triggered = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Alert {self.user.username} - {self.symbol.symbol} {self.indicator_type}"
