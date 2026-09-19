from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from .constants import SUPPORTED_MARKETS, TIMEFRAMES


class MarketSymbol(models.Model):
    broker = models.CharField(max_length=80, default="deriv")
    symbol = models.CharField(max_length=40, unique=True, db_index=True)
    display_name = models.CharField(max_length=160)
    market = models.CharField(max_length=80, choices=[(m, m) for m in SUPPORTED_MARKETS], db_index=True)
    sub_market = models.CharField(max_length=120, blank=True, db_index=True)
    pip_size = models.PositiveSmallIntegerField(default=2)
    tick_size = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    currency = models.CharField(max_length=12, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_tradable = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["market", "symbol"]
        indexes = [models.Index(fields=["broker", "symbol"]), models.Index(fields=["market", "sub_market"])]

    def __str__(self):
        return self.symbol


class Tick(models.Model):
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name="ticks")
    bid = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    ask = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    quote = models.DecimalField(max_digits=20, decimal_places=8)
    spread = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    epoch = models.BigIntegerField(db_index=True)
    volume = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    received_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-epoch"]
        unique_together = [("symbol", "epoch", "quote")]
        indexes = [models.Index(fields=["symbol", "-epoch"]), models.Index(fields=["received_at"])]


class Candle(models.Model):
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name="candles")
    timeframe = models.CharField(max_length=8, choices=[(k, k) for k in TIMEFRAMES], db_index=True)
    open = models.DecimalField(max_digits=20, decimal_places=8)
    high = models.DecimalField(max_digits=20, decimal_places=8)
    low = models.DecimalField(max_digits=20, decimal_places=8)
    close = models.DecimalField(max_digits=20, decimal_places=8)
    volume = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    epoch = models.BigIntegerField(db_index=True)
    source = models.CharField(max_length=32, default="tick_stream", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-epoch"]
        unique_together = [("symbol", "timeframe", "epoch")]
        indexes = [models.Index(fields=["symbol", "timeframe", "-epoch"])]


class MarketSnapshot(models.Model):
    symbol = models.OneToOneField(MarketSymbol, on_delete=models.CASCADE, related_name="snapshot")
    last_price = models.DecimalField(max_digits=20, decimal_places=8)
    bid = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    ask = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    spread = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    high = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    low = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    change = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    change_percent = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    volume = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)


class Subscription(models.Model):
    STATUS_CHOICES = [("active", "Active"), ("paused", "Paused"), ("cancelled", "Cancelled")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="market_subscriptions")
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name="subscriptions")
    timeframe = models.CharField(max_length=8, choices=[(k, k) for k in TIMEFRAMES], default="tick")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "symbol", "timeframe")]


class MarketStatistics(models.Model):
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name="statistics")
    average_spread = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    highest_price = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    lowest_price = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    highest_volume = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    tick_count = models.PositiveBigIntegerField(default=0)
    average_tick_rate = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    market_volatility = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    average_volume = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    tick_frequency = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["symbol", "-created_at"])]


class CandleBackfillRun(models.Model):
    """Durable control record for the one-time historical warm-up job."""

    STATUS_CHOICES = [
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    scope = models.CharField(max_length=32, unique=True, default="initial")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="running", db_index=True)
    count = models.PositiveIntegerField(default=5000)
    symbol = models.CharField(max_length=40, blank=True)
    task_id = models.CharField(max_length=255, blank=True, db_index=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="candle_backfill_runs",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    dispatch_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    current_symbol = models.CharField(max_length=40, blank=True)
    current_timeframe = models.CharField(max_length=32, blank=True)
    worker_hostname = models.CharField(max_length=255, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self):
        return f"{self.scope}:{self.status}"


class CandleBackfillEvent(models.Model):
    """Durable operator log line for a candle-backfill run."""

    LEVEL_CHOICES = [
        ("info", "Info"),
        ("notice", "Notice"),
        ("warning", "Warning"),
        ("error", "Error"),
        ("success", "Success"),
    ]

    EVENT_TYPES = [
        ("dispatch", "Dispatch"),
        ("worker_received", "Worker received"),
        ("worker_started", "Worker started"),
        ("symbol_started", "Symbol started"),
        ("timeframe", "Timeframe"),
        ("symbol_completed", "Symbol completed"),
        ("heartbeat", "Heartbeat"),
        ("warning", "Warning"),
        ("error", "Error"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("recovered", "Recovered"),
    ]

    run = models.ForeignKey(CandleBackfillRun, on_delete=models.CASCADE, related_name="events")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    level = models.CharField(max_length=16, choices=LEVEL_CHOICES, default="info", db_index=True)
    event_type = models.CharField(max_length=32, choices=EVENT_TYPES, default="heartbeat")
    message = models.TextField()
    symbol = models.CharField(max_length=40, blank=True)
    timeframe = models.CharField(max_length=32, blank=True)
    task_id = models.CharField(max_length=255, blank=True)
    worker_hostname = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["run", "-created_at"]),
            models.Index(fields=["run", "level", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.run_id}:{self.level}:{self.message[:80]}"
