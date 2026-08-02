from django.db import models
from django.contrib.auth.models import User


class Tick(models.Model):
    symbol = models.CharField(max_length=20)
    price = models.FloatField()
    epoch = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["symbol"]),
            models.Index(fields=["epoch"]),
        ]


class Strategy(models.Model):
    """Master strategy registry"""
    STRATEGY_TYPES = [
        ('TREND', 'Trend Following'),
        ('MEAN_REV', 'Mean Reversion'),
        ('BREAKOUT', 'Breakout'),
        ('MOMENTUM', 'Momentum'),
        ('SCALP', 'Scalping'),
        ('VOLATILITY', 'Volatility Trading'),
    ]

    name = models.CharField(max_length=100, unique=True)
    strategy_type = models.CharField(max_length=20, choices=STRATEGY_TYPES)
    description = models.TextField(blank=True)
    config = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    is_paper_only = models.BooleanField(default=False)
    version = models.IntegerField(default=1)
    total_trades = models.IntegerField(default=0)
    winning_trades = models.IntegerField(default=0)
    losing_trades = models.IntegerField(default=0)
    win_rate = models.FloatField(default=0)
    total_pnl = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.name} ({self.strategy_type})"


class Trade(models.Model):
    """Trade execution record"""
    TRADE_STATUS = [
        ('OPEN', 'Open'),
        ('CLOSED', 'Closed'),
        ('CANCELLED', 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    strategy_fk = models.ForeignKey(Strategy, on_delete=models.SET_NULL, null=True, blank=True, related_name='trades')
    strategy = models.CharField(max_length=100, blank=True)  # Legacy
    
    symbol = models.CharField(max_length=20)
    contract_type = models.CharField(max_length=10)
    entry_price = models.FloatField()
    stake = models.FloatField()
    exit_price = models.FloatField(null=True, blank=True)
    
    profit = models.FloatField(default=0)
    profit_pct = models.FloatField(default=0)
    status = models.CharField(max_length=20, choices=TRADE_STATUS, default='OPEN')
    
    strategy_confidence = models.FloatField(default=0)
    entry_reason = models.TextField(blank=True)
    exit_reason = models.TextField(blank=True)
    indicators_snapshot = models.JSONField(default=dict, blank=True)
    is_paper = models.BooleanField(default=False)
    
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-opened_at']

    def __str__(self):
        return f"{self.symbol} {self.contract_type} - {self.status}"


class BacktestResult(models.Model):
    """Backtest result with metrics"""
    strategy_fk = models.ForeignKey(Strategy, on_delete=models.CASCADE, null=True, blank=True, related_name='backtest_results')
    strategy = models.CharField(max_length=100, blank=True)  # Legacy
    
    symbol = models.CharField(max_length=20, default='R_75')
    timeframe = models.CharField(max_length=10, default='M1')
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    initial_balance = models.FloatField(default=1000)
    
    total_trades = models.IntegerField()
    wins = models.IntegerField()
    losses = models.IntegerField()
    win_rate = models.FloatField()
    expectancy = models.FloatField()
    
    sharpe_ratio = models.FloatField()
    sortino_ratio = models.FloatField(default=0)
    max_drawdown = models.FloatField()
    max_drawdown_pct = models.FloatField(default=0)
    profit_factor = models.FloatField(default=0)
    
    total_profit = models.FloatField(default=0)
    total_profit_pct = models.FloatField(default=0)
    final_balance = models.FloatField(default=1000)
    
    trades_log = models.JSONField(default=list, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.strategy} Backtest"


class Candle(models.Model):
    """OHLCV candle data"""
    symbol = models.CharField(max_length=20)
    timeframe = models.CharField(max_length=10)
    open = models.FloatField()
    high = models.FloatField()
    low = models.FloatField()
    close = models.FloatField()
    volume = models.IntegerField(default=0)
    timestamp = models.DateTimeField()
    is_bullish = models.BooleanField(default=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.symbol} {self.timeframe}"


class Signal(models.Model):
    """Trading signal"""
    SIGNAL_DIRECTION = [
        ('BUY', 'Buy'),
        ('SELL', 'Sell'),
        ('NEUTRAL', 'Neutral'),
    ]

    strategy_fk = models.ForeignKey(Strategy, on_delete=models.CASCADE, null=True, blank=True, related_name='signals')
    strategy = models.CharField(max_length=100, blank=True)  # Legacy
    
    symbol = models.CharField(max_length=20)
    direction = models.CharField(max_length=10, choices=SIGNAL_DIRECTION)
    confidence = models.FloatField()
    
    timeframe = models.CharField(max_length=10, blank=True)
    indicators_used = models.JSONField(default=list, blank=True)
    market_regime = models.CharField(max_length=20, blank=True)
    was_executed = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.strategy} - {self.direction}"


class PerformanceSnapshot(models.Model):
    """Account performance snapshot"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    
    balance = models.FloatField()
    equity = models.FloatField()
    drawdown = models.FloatField()
    drawdown_pct = models.FloatField(default=0)
    
    pnl = models.FloatField()
    pnl_pct = models.FloatField(default=0)
    
    total_trades = models.IntegerField(default=0)
    win_rate = models.FloatField(default=0)
    
    is_paper = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Performance {self.created_at}"


class AIModel(models.Model):
    """Registry for trained AI models and metadata."""
    name = models.CharField(max_length=100)
    model_type = models.CharField(max_length=50)
    storage_path = models.CharField(max_length=255)
    version = models.CharField(max_length=50, default='1')
    trained_at = models.DateTimeField(null=True, blank=True)
    metrics = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} v{self.version} ({self.model_type})"


class DerivAccount(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    account_id = models.CharField(max_length=50)
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True, null=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
