from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Notification(models.Model):
    """Persisted user notification history for trade and system alerts."""

    ALERT_TYPES = [
        ('trade_opened', 'Trade Opened'),
        ('trade_closed', 'Trade Closed'),
        ('profit_target', 'Profit Target Reached'),
        ('drawdown_warning', 'Drawdown Warning'),
    ]

    CHANNEL_CHOICES = [
        ('email', 'Email'),
        ('telegram', 'Telegram'),
        ('push', 'Push'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPES)
    message = models.TextField()
    channels = models.JSONField(default=list, blank=True)
    delivered_channels = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, default='sent')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.alert_type}"
