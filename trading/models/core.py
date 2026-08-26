from django.db import models
from django.contrib.auth.models import User


class Tick(models.Model):
    symbol = models.CharField(max_length=20)
    price = models.FloatField()
    epoch = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["symbol"]), models.Index(fields=["epoch"])]


class Strategy(models.Model):
    """Master strategy registry"""
    STRATEGY_TYPES = [('TREND', 'Trend Following'), ('MEAN_REV', 'Mean Reversion'), ('BREAKOUT', 'Breakout'), ('MOMENTUM', 'Momentum'), ('SCALP', 'Scalping'), ('VOLATILITY', 'Volatility Trading')]
    name = models.CharField(max_length=100, unique=True)
    strategy_type = models.CharField(max_length=20, choices=STRATEGY_TYPES)
    description = models.TextField()
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
    class Meta: ordering = ['-updated_at']
    def __str__(self): return f"{self.name} ({self.strategy_type})"


class Trade(models.Model):
    """Trade execution record"""
    TRADE_STATUS = [('NEW','New'),('VALIDATED','Validated'),('QUEUED','Queued'),('SUBMITTED','Submitted'),('ACCEPTED','Accepted'),('OPEN','Open'),('PARTIALLY_CLOSED','Partially Closed'),('CLOSED','Closed'),('ARCHIVED','Archived'),('CANCELLED','Cancelled')]
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    strategy_fk = models.ForeignKey(Strategy, on_delete=models.SET_NULL, null=True, blank=True, related_name='trades')
    strategy = models.CharField(max_length=100, blank=True)
    symbol = models.CharField(max_length=20)
    contract_type = models.CharField(max_length=10)
    entry_price = models.FloatField()
    stake = models.FloatField()
    exit_price = models.FloatField(null=True, blank=True)
    profit = models.FloatField(default=0)
    profit_pct = models.FloatField(default=0)
    status = models.CharField(max_length=20, choices=TRADE_STATUS, default='OPEN')
    client_request_id = models.CharField(max_length=80, blank=True, db_index=True)
    broker_reference = models.CharField(max_length=160, blank=True, db_index=True)
    strategy_confidence = models.FloatField(default=0)
    entry_reason = models.TextField(blank=True)
    exit_reason = models.TextField(blank=True)
    indicators_snapshot = models.JSONField(default=dict, blank=True)
    is_paper = models.BooleanField(default=False)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ['-opened_at']
        indexes = [models.Index(fields=['user','status','-opened_at']), models.Index(fields=['symbol','status'])]
        constraints = [models.UniqueConstraint(fields=['user','client_request_id'], condition=~models.Q(client_request_id=''), name='legacy_trading_unique_trade_client_request')]
    def __str__(self): return f"{self.symbol} {self.contract_type} - {self.status}"


class TradeStateTransition(models.Model):
    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name='state_transitions')
    from_state = models.CharField(max_length=20, blank=True)
    to_state = models.CharField(max_length=20)
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['trade','-created_at']), models.Index(fields=['to_state','-created_at'])]


class TradeExecution(models.Model):
    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name='executions')
    broker = models.CharField(max_length=60, default='deriv')
    status = models.CharField(max_length=40, db_index=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    latency_ms = models.FloatField(default=0)
    attempt = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['trade','-created_at']), models.Index(fields=['broker','status'])]


class PortfolioSnapshot(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='portfolio_snapshots')
    balance = models.FloatField(default=0)
    equity = models.FloatField(default=0)
    margin = models.FloatField(default=0)
    open_positions = models.PositiveIntegerField(default=0)
    daily_pnl = models.FloatField(default=0)
    risk_utilization = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user','-created_at'])]


class StrategyPerformance(models.Model):
    strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE, related_name='performance_snapshots')
    symbol = models.CharField(max_length=20, blank=True)
    total_trades = models.PositiveIntegerField(default=0)
    win_rate = models.FloatField(default=0)
    profit_factor = models.FloatField(default=0)
    max_drawdown = models.FloatField(default=0)
    net_pnl = models.FloatField(default=0)
    snapshot_at = models.DateTimeField(auto_now_add=True, db_index=True)
    class Meta:
        ordering = ['-snapshot_at']
        indexes = [models.Index(fields=['strategy','-snapshot_at']), models.Index(fields=['symbol','-snapshot_at'])]


class RiskEvent(models.Model):
    SEVERITY_CHOICES = [('INFO','Info'),('WARNING','Warning'),('CRITICAL','Critical')]
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    trade = models.ForeignKey(Trade, on_delete=models.SET_NULL, null=True, blank=True, related_name='risk_events')
    event_type = models.CharField(max_length=80, db_index=True)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='INFO', db_index=True)
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['event_type','severity','-created_at'])]


class ConnectionLog(models.Model):
    broker = models.CharField(max_length=60, db_index=True)
    account_id = models.CharField(max_length=80, blank=True, db_index=True)
    status = models.CharField(max_length=40, db_index=True)
    latency_ms = models.FloatField(default=0)
    message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['broker','status','-created_at'])]


class PredictionHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    symbol = models.CharField(max_length=20, db_index=True)
    model_name = models.CharField(max_length=120, db_index=True)
    prediction = models.JSONField(default=dict)
    confidence = models.FloatField(default=0)
    actual_outcome = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['symbol','model_name','-created_at'])]


class UserPreferences(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='trading_preferences')
    default_symbol = models.CharField(max_length=20, default='R_75')
    default_strategy = models.ForeignKey(Strategy, on_delete=models.SET_NULL, null=True, blank=True)
    trading_enabled = models.BooleanField(default=False)
    risk_percent = models.FloatField(default=0.02)
    max_daily_loss = models.FloatField(default=0)
    max_exposure = models.FloatField(default=0)
    notification_preferences = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class MarketCandle(models.Model):
    symbol = models.CharField(max_length=20)
    timeframe = models.CharField(max_length=10)
    timestamp = models.DateTimeField()
    open = models.FloatField()
    high = models.FloatField()
    low = models.FloatField()
    close = models.FloatField()
    volume = models.FloatField(default=0)
    source = models.CharField(max_length=60, default='deriv')
    class Meta:
        ordering = ['timestamp']
        indexes = [models.Index(fields=['symbol','timeframe','timestamp'])]
        constraints = [models.UniqueConstraint(fields=['symbol','timeframe','timestamp','source'], name='unique_market_candle')]


class BacktestResult(models.Model):
    strategy_fk = models.ForeignKey(Strategy, on_delete=models.CASCADE, null=True, blank=True, related_name='backtest_results')
    strategy = models.CharField(max_length=100, blank=True)
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
    class Meta: ordering = ['-created_at']
    def __str__(self): return f"{self.strategy} Backtest"


class Candle(models.Model):
    symbol = models.CharField(max_length=20)
    timeframe = models.CharField(max_length=10)
    open = models.FloatField()
    high = models.FloatField()
    low = models.FloatField()
    close = models.FloatField()
    volume = models.IntegerField(default=0)
    timestamp = models.DateTimeField()
    is_bullish = models.BooleanField(default=True)
    class Meta: ordering = ['timestamp']


class Signal(models.Model):
    SIGNAL_DIRECTION = [('BUY','Buy'),('SELL','Sell'),('NEUTRAL','Neutral')]
    strategy_fk = models.ForeignKey(Strategy, on_delete=models.CASCADE, null=True, blank=True, related_name='signals')
    strategy = models.CharField(max_length=100, blank=True)
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
        indexes = [models.Index(fields=['symbol', '-created_at'], name='signal_symbol_created_idx')]
    def __str__(self): return f"{self.strategy} - {self.direction}"


class PerformanceSnapshot(models.Model):
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
    class Meta: ordering = ['-created_at']
    def __str__(self): return f"Performance {self.created_at}"


class AIModel(models.Model):
    name = models.CharField(max_length=100)
    model_type = models.CharField(max_length=50)
    storage_path = models.CharField(max_length=255)
    version = models.CharField(max_length=50, default='1')
    trained_at = models.DateTimeField(null=True, blank=True)
    metrics = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at']
    def __str__(self): return f"{self.name} v{self.version} ({self.model_type})"


class DerivAccount:
    """Deprecated compatibility symbol. Canonical broker accounts live in apps.brokers.models.BrokerAccount."""
    from apps.brokers.models import BrokerAccount as _CanonicalBrokerAccount
    DoesNotExist = _CanonicalBrokerAccount.DoesNotExist
