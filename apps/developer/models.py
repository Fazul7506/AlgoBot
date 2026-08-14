from django.conf import settings
from django.db import models
from django.utils import timezone

STATUS_CHOICES = [(s, s.title()) for s in ("active", "inactive", "revoked", "expired", "pending")]


class APIKey(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="developer_api_keys")
    name = models.CharField(max_length=120)
    key = models.CharField(max_length=128, unique=True, db_index=True)
    secret = models.CharField(max_length=255)
    previous_secret = models.CharField(max_length=255, blank=True, default="")
    previous_secret_expires_at = models.DateTimeField(null=True, blank=True)
    permissions = models.JSONField(default=list, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="active", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_active(self):
        if self.status != "active":
            return False
        if self.expires_at and self.expires_at <= timezone.now():
            return False
        return True


class OAuthClient(models.Model):
    name = models.CharField(max_length=120)
    client_id = models.CharField(max_length=128, unique=True)
    client_secret = models.CharField(max_length=255)
    redirect_uri = models.URLField()
    grant_type = models.CharField(max_length=40, default="authorization_code")
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="active")


class Plugin(models.Model):
    name = models.CharField(max_length=120)
    version = models.CharField(max_length=40)
    author = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=40, db_index=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="pending")
    entry_point = models.CharField(max_length=255)
    class Meta:
        unique_together = [("name", "version")]


class Webhook(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="developer_webhooks")
    url = models.URLField()
    secret = models.CharField(max_length=255)
    events = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class WebhookDelivery(models.Model):
    webhook = models.ForeignKey(Webhook, on_delete=models.CASCADE, related_name="deliveries")
    event = models.CharField(max_length=120)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=24, default="pending")
    attempts = models.PositiveIntegerField(default=0)
    response_status = models.PositiveIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    last_error = models.TextField(blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class APIUsageEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="developer_api_usage")
    api_key = models.ForeignKey(APIKey, null=True, blank=True, on_delete=models.SET_NULL, related_name="usage_events")
    method = models.CharField(max_length=12)
    path = models.CharField(max_length=500)
    status_code = models.PositiveIntegerField(default=200)
    latency_ms = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class RateLimitEvent(models.Model):
    api_key = models.ForeignKey(APIKey, null=True, blank=True, on_delete=models.SET_NULL, related_name="rate_limit_events")
    identity = models.CharField(max_length=255, db_index=True)
    path = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class SDKRelease(models.Model):
    language = models.CharField(max_length=40, db_index=True)
    version = models.CharField(max_length=40)
    release_notes = models.TextField(blank=True)
    download_url = models.URLField()
    class Meta:
        unique_together = [("language", "version")]


class Integration(models.Model):
    provider = models.CharField(max_length=80, db_index=True)
    configuration = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="inactive")
    created_at = models.DateTimeField(auto_now_add=True)
