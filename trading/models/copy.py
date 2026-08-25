from django.db import models
from django.conf import settings


class CopyFollow(models.Model):
    """Represents a follower following a leader (trader) with allocation settings."""

    ALLOCATION_TYPE_CHOICES = [
        ('PERCENT', 'Percent of follower equity'),
        ('FIXED', 'Fixed amount'),
    ]

    leader = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='followers')
    follower = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='following')
    allocation_type = models.CharField(max_length=10, choices=ALLOCATION_TYPE_CHOICES, default='PERCENT')
    allocation_value = models.FloatField(default=10.0, help_text='Percent when PERCENT, amount in account currency when FIXED')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('leader', 'follower')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.follower.username} -> {self.leader.username} ({self.allocation_type}={self.allocation_value})"


class LeaderStats(models.Model):
    """Cached performance metrics and follower counts for a leader/trader."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='leader_stats')
    followers_count = models.IntegerField(default=0)
    assets_under_management = models.FloatField(default=0.0)
    total_trades = models.IntegerField(default=0)
    win_rate = models.FloatField(default=0.0)
    avg_return_pct = models.FloatField(default=0.0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-assets_under_management']

    def __str__(self):
        return f"LeaderStats {self.user.username} (followers={self.followers_count})"


class CopyTrade(models.Model):
    """Record that a leader trade was mirrored for a follower."""

    leader_trade_id = models.CharField(max_length=64, help_text='Original leader trade identifier')
    follower = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='copied_trades')
    # This model lives in the legacy_trading Django app. Keep the lazy relation
    # explicit so Django resolves it against the app's unique label rather than
    # the old/default "trading" label.
    follower_trade = models.ForeignKey(
        'legacy_trading.Trade',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='as_copied_trade',
    )
    amount = models.FloatField()
    status = models.CharField(max_length=20, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"CopyTrade leader_trade={self.leader_trade_id} follower={self.follower.username} amount={self.amount}"
