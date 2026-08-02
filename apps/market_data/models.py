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
