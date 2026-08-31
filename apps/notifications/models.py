import uuid

from django.conf import settings
from django.db import models


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enterprise_notifications")
    title = models.CharField(max_length=220)
    message = models.TextField()
    category = models.CharField(max_length=40, default="general", db_index=True)
    priority = models.CharField(max_length=24, default="info", db_index=True)
    status = models.CharField(max_length=24, default="queued", db_index=True)
    channel = models.CharField(max_length=40, default="in_app", db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_error = models.TextField(blank=True)
    telegram_message_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status", "priority"]),
            models.Index(fields=["channel", "status", "available_at"], name="notif_chan_status_avail_idx"),
        ]


class NotificationTemplate(models.Model):
    name = models.CharField(max_length=180, db_index=True)
    category = models.CharField(max_length=40, default="general", db_index=True)
    subject = models.CharField(max_length=220, blank=True)
    body = models.TextField()
    language = models.CharField(max_length=16, default="en")
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)


class NotificationPreference(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_preferences")
    channel = models.CharField(max_length=40, db_index=True)
    enabled = models.BooleanField(default=True)
    quiet_hours = models.JSONField(default=dict, blank=True)
    digest_frequency = models.CharField(max_length=24, default="immediate")

    class Meta:
        unique_together = ("user", "channel")


class NotificationChannelConnection(models.Model):
    PROVIDER_CHOICES = (("gmail", "Gmail"), ("telegram", "Telegram"))
    STATUS_CHOICES = (("pending", "Pending"), ("verified", "Verified"), ("revoked", "Revoked"), ("error", "Error"))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_channel_connections")
    provider = models.CharField(max_length=24, choices=PROVIDER_CHOICES, db_index=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="pending", db_index=True)
    address = models.CharField(max_length=320, blank=True)
    external_id = models.CharField(max_length=180, blank=True)
    access_token = models.TextField(blank=True)
    refresh_token = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    verification_code_hash = models.CharField(max_length=128, blank=True)
    verification_expires_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "provider"], name="uniq_notification_channel_provider")]
        indexes = [models.Index(fields=["user", "provider", "status"])]


class DeliveryLog(models.Model):
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name="delivery_logs")
    channel = models.CharField(max_length=40, db_index=True)
    status = models.CharField(max_length=24, default="queued", db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    provider = models.CharField(max_length=80, blank=True)
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)


class NotificationRule(models.Model):
    name = models.CharField(max_length=180)
    event = models.CharField(max_length=120, db_index=True)
    condition = models.JSONField(default=dict, blank=True)
    priority = models.PositiveSmallIntegerField(default=100, db_index=True)
    enabled = models.BooleanField(default=True, db_index=True)


class Broadcast(models.Model):
    title = models.CharField(max_length=220)
    message = models.TextField()
    target_group = models.CharField(max_length=80, default="all_users", db_index=True)
    status = models.CharField(max_length=24, default="queued", db_index=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)


class TelegramUpdate(models.Model):
    update_id = models.BigIntegerField(unique=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at"]


class TelegramRuntimeState(models.Model):
    singleton = models.PositiveSmallIntegerField(primary_key=True, default=1, serialize=False)
    mode = models.CharField(max_length=16, default="webhook")
    status = models.CharField(max_length=24, default="starting")
    started_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_update_at = models.DateTimeField(null=True, blank=True)
    last_delivery_at = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    reconnect_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
