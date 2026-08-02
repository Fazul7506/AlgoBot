from django.db import models
from django.utils import timezone
import uuid


class MarketSymbol(models.Model):
    """Market symbols database with metadata"""
    
    MARKET_TYPE_CHOICES = [
        ('VOLATILITY', 'Volatility Index'),
        ('BOOM_CRASH', 'Boom/Crash'),
        ('FOREX', 'Foreign Exchange'),
        ('SYNTHETIC', 'Synthetic Index'),
        ('CRYPTO', 'Cryptocurrency'),
        ('COMMODITY', 'Commodity'),
    ]
    
    TIMEFRAME_CHOICES = [
        ('M1', '1 Minute'),
        ('M5', '5 Minutes'),
        ('M15', '15 Minutes'),
        ('M30', '30 Minutes'),
        ('H1', '1 Hour'),
        ('H4', '4 Hours'),
        ('D1', '1 Day'),
    ]
    
    symbol = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=200)
    market_type = models.CharField(max_length=20, choices=MARKET_TYPE_CHOICES)
    
    # Symbol metadata
    description = models.TextField(blank=True)
    min_stake = models.FloatField(default=0.35)
    max_stake = models.FloatField(default=50000.0)
    pip_size = models.FloatField(default=0.0001)
    
    # Streaming configuration
    is_active = models.BooleanField(default=True)
    is_tradeable = models.BooleanField(default=True)
    supported_timeframes = models.JSONField(default=list)  # e.g., ['M1', 'M5', 'H1']
    
    # Market hours
    market_open = models.TimeField(null=True, blank=True)
    market_close = models.TimeField(null=True, blank=True)
    timezone = models.CharField(max_length=100, default='UTC')
    
    # Statistics
    last_tick_time = models.DateTimeField(null=True, blank=True)
    avg_spread = models.FloatField(default=0.0)
    trading_volume_24h = models.FloatField(default=0.0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['market_type', 'symbol']
        indexes = [
            models.Index(fields=['symbol']),
            models.Index(fields=['market_type', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.symbol} ({self.display_name})"


class PriceHistory(models.Model):
    """Aggregated OHLC price history for charting"""
    
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name='price_history')
    timeframe = models.CharField(max_length=10)
    
    # OHLC data
    open = models.FloatField()
    high = models.FloatField()
    low = models.FloatField()
    close = models.FloatField()
    volume = models.BigIntegerField(default=0)
    
    # Tick count for this candle
    tick_count = models.IntegerField(default=0)
    
    # Candle timing
    candle_time = models.DateTimeField()  # Start of candle
    candle_end_time = models.DateTimeField()  # End of candle
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-candle_time']
        indexes = [
            models.Index(fields=['symbol', 'timeframe', '-candle_time']),
            models.Index(fields=['candle_time']),
        ]
        unique_together = [['symbol', 'timeframe', 'candle_time']]
    
    def __str__(self):
        return f"{self.symbol.symbol} {self.timeframe} {self.candle_time}"


class MarketSnapshot(models.Model):
    """Real-time market snapshot for quick lookups"""
    
    symbol = models.OneToOneField(MarketSymbol, on_delete=models.CASCADE, related_name='snapshot')
    
    # Current price
    current_bid = models.FloatField()
    current_ask = models.FloatField()
    last_price = models.FloatField()
    
    # 24h data
    high_24h = models.FloatField(default=0.0)
    low_24h = models.FloatField(default=0.0)
    
    # Change metrics
    change_24h = models.FloatField(default=0.0)
    change_pct_24h = models.FloatField(default=0.0)
    
    # Spread
    bid_ask_spread = models.FloatField(default=0.0)
    spread_pct = models.FloatField(default=0.0)
    
    # Volume
    volume_24h = models.BigIntegerField(default=0)
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"Snapshot: {self.symbol.symbol} @ {self.last_price}"


class TickData(models.Model):
    """Raw tick data for backtesting and analysis"""
    
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name='tick_data')
    
    # Price data
    bid = models.FloatField()
    ask = models.FloatField()
    
    # Timing
    epoch = models.BigIntegerField()  # Unix timestamp in milliseconds
    received_at = models.DateTimeField(auto_now_add=True)
    
    # Metadata
    spread = models.FloatField()
    tick_number = models.BigIntegerField()
    
    class Meta:
        ordering = ['-epoch']
        indexes = [
            models.Index(fields=['symbol', '-epoch']),
            models.Index(fields=['epoch']),
        ]
    
    def __str__(self):
        return f"{self.symbol.symbol} Tick @ {self.epoch}"


class DataStreamSession(models.Model):
    """Track active websocket sessions for market data streaming"""
    
    STATUS_CHOICES = [
        ('CONNECTING', 'Connecting'),
        ('CONNECTED', 'Connected'),
        ('SUBSCRIBED', 'Subscribed'),
        ('DISCONNECTED', 'Disconnected'),
        ('ERROR', 'Error'),
    ]
    
    session_id = models.CharField(max_length=100, unique=True)
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name='stream_sessions')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='CONNECTING')
    
    # Connection info
    connected_at = models.DateTimeField(null=True, blank=True)
    disconnected_at = models.DateTimeField(null=True, blank=True)
    
    # Statistics
    ticks_received = models.BigIntegerField(default=0)
    bytes_received = models.BigIntegerField(default=0)
    
    # Last activity
    last_tick_at = models.DateTimeField(null=True, blank=True)
    
    # Error handling
    error_count = models.IntegerField(default=0)
    last_error = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['session_id']),
            models.Index(fields=['status', '-created_at']),
        ]
    
    def __str__(self):
        return f"Session {self.session_id[:10]} - {self.symbol.symbol}"
