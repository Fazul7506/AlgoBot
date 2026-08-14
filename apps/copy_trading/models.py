from django.conf import settings
from django.db import models
from . import constants as c
class SignalProvider(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='signal_provider_profiles'); display_name=models.CharField(max_length=120); bio=models.TextField(blank=True); verification_status=models.CharField(max_length=32,default='pending'); experience_level=models.CharField(max_length=32,blank=True); country=models.CharField(max_length=80,blank=True); followers=models.PositiveIntegerField(default=0); rating=models.FloatField(default=0); created_at=models.DateTimeField(auto_now_add=True)
class TradingStrategy(models.Model):
    provider=models.ForeignKey(SignalProvider,on_delete=models.CASCADE,related_name='strategies'); name=models.CharField(max_length=160); description=models.TextField(blank=True); category=models.CharField(max_length=40,choices=[(x,x.title()) for x in c.STRATEGY_CATEGORIES]); risk_level=models.CharField(max_length=32,default='medium'); subscription_price=models.DecimalField(max_digits=10,decimal_places=2,default=0); visibility=models.CharField(max_length=32,default='public'); performance_score=models.FloatField(default=0)
class StrategySubscription(models.Model):
    strategy=models.ForeignKey(TradingStrategy,on_delete=models.CASCADE,related_name='subscriptions'); follower=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='strategy_subscriptions'); status=models.CharField(max_length=32,default='active'); started_at=models.DateTimeField(auto_now_add=True); expires_at=models.DateTimeField(null=True,blank=True)
class TradeMirror(models.Model):
    provider_trade=models.CharField(max_length=120); follower_trade=models.CharField(max_length=120,blank=True); allocation=models.DecimalField(max_digits=10,decimal_places=4,default=1); multiplier=models.DecimalField(max_digits=10,decimal_places=4,default=1); status=models.CharField(max_length=32,default='pending')
class RevenueShare(models.Model):
    provider=models.ForeignKey(SignalProvider,on_delete=models.CASCADE); subscriber=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE); amount=models.DecimalField(max_digits=12,decimal_places=2); commission=models.DecimalField(max_digits=12,decimal_places=2,default=0); paid_at=models.DateTimeField(null=True,blank=True)
class PerformanceSnapshot(models.Model):
    strategy=models.ForeignKey(TradingStrategy,on_delete=models.CASCADE,related_name='performance_snapshots'); daily_return=models.FloatField(default=0); monthly_return=models.FloatField(default=0); yearly_return=models.FloatField(default=0); drawdown=models.FloatField(default=0); sharpe=models.FloatField(default=0); profit_factor=models.FloatField(default=0); win_rate=models.FloatField(default=0)
class Leaderboard(models.Model):
    strategy=models.ForeignKey(TradingStrategy,on_delete=models.CASCADE); provider=models.ForeignKey(SignalProvider,on_delete=models.CASCADE); ranking=models.PositiveIntegerField(); score=models.FloatField(default=0); period=models.CharField(max_length=32,default='monthly')


class CopyProvider(models.Model):
    """Tenant-scoped copy-trading provider exposed by the Phase 17 API."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="copy_providers",
    )
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180)
    status = models.CharField(max_length=32, default="active")
    strategy = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    risk_score = models.FloatField(default=0)
    return_pct = models.FloatField(default=0)
    win_rate = models.FloatField(default=0)
    max_drawdown_pct = models.FloatField(default=0)
    followers_count = models.PositiveIntegerField(default=0)
    min_allocation = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    max_allocation = models.DecimalField(max_digits=12, decimal_places=2, default=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "slug"],
                name="copy_provider_tenant_slug_uniq",
            )
        ]
        ordering = ["-return_pct", "-followers_count", "name"]

    def __str__(self):
        return self.name


class CopyFollower(models.Model):
    """Follower configuration and authoritative risk limits."""

    STATUS_CHOICES = [
        ("active", "Active"),
        ("paused", "Paused"),
        ("stopped", "Stopped"),
    ]
    ALLOCATION_MODES = [
        ("fixed", "Fixed"),
        ("proportional", "Proportional"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="copy_followers",
    )
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="copy_followers",
    )
    provider = models.ForeignKey(
        CopyProvider,
        on_delete=models.CASCADE,
        related_name="followers_profiles",
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="active")
    allocation = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    allocation_mode = models.CharField(
        max_length=32,
        choices=ALLOCATION_MODES,
        default="fixed",
    )
    max_daily_loss_pct = models.DecimalField(
        max_digits=8, decimal_places=2, default=3
    )
    max_drawdown_pct = models.DecimalField(
        max_digits=8, decimal_places=2, default=5
    )
    max_trade_stake = models.DecimalField(
        max_digits=12, decimal_places=2, default=10
    )
    max_concurrent_trades = models.PositiveIntegerField(default=3)
    pause_on_loss_streak = models.PositiveIntegerField(default=3)
    copy_multiplier = models.DecimalField(
        max_digits=8, decimal_places=4, default=1
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "tenant", "provider"],
                name="copy_follower_user_tenant_provider_uniq",
            )
        ]

    def __str__(self):
        return f"{self.user_id}:{self.provider_id}"


class CopySubscription(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("paused", "Paused"),
        ("cancelled", "Cancelled"),
    ]

    follower = models.OneToOneField(
        CopyFollower,
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="active")
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Subscription {self.id}"


class CopyTrade(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("open", "Open"),
        ("closed", "Closed"),
        ("cancelled", "Cancelled"),
    ]

    follower = models.ForeignKey(
        CopyFollower,
        on_delete=models.CASCADE,
        related_name="trades",
    )
    provider_trade = models.CharField(max_length=120, blank=True)
    symbol = models.CharField(max_length=80)
    direction = models.CharField(max_length=20)
    stake = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    source_stake = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    profit = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="pending")
    rejection_reason = models.TextField(blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-opened_at", "-created_at"]

    def __str__(self):
        return f"{self.symbol}:{self.id}"
