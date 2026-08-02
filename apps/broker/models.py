"""Broker-agnostic models for accounts, tokens, permissions, and connection telemetry."""

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.services.encryption_service import CredentialEncryptionService


class Broker(models.Model):
    STATUS_CHOICES = [("active", "Active"), ("disabled", "Disabled"), ("maintenance", "Maintenance")]
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=80, unique=True)
    logo = models.ImageField(upload_to="brokers/", blank=True, null=True)
    website = models.URLField(blank=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class BrokerAccount(models.Model):
    ACCOUNT_TYPES = [("demo", "Demo"), ("real", "Real")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="broker_accounts")
    broker = models.ForeignKey(Broker, on_delete=models.CASCADE, related_name="accounts")
    broker_account_id = models.CharField(max_length=120)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, default="demo")
    currency = models.CharField(max_length=12, blank=True)
    balance = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    equity = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    margin = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    is_default = models.BooleanField(default=False)
    is_connected = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("broker", "broker_account_id")]
        indexes = [models.Index(fields=["user", "is_default"]), models.Index(fields=["broker", "is_connected"])]

    def __str__(self) -> str:
        return f"{self.broker.slug}:{self.broker_account_id}"


class BrokerToken(models.Model):
    STATUS_CHOICES = [("active", "Active"), ("expired", "Expired"), ("revoked", "Revoked")]
    broker_account = models.OneToOneField(BrokerAccount, on_delete=models.CASCADE, related_name="token")
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_refresh = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

    def set_access_token(self, token: str) -> None:
        self.access_token = CredentialEncryptionService().encrypt(token)

    def get_access_token(self) -> str:
        return CredentialEncryptionService().decrypt(self.access_token)

    def set_refresh_token(self, token: str) -> None:
        self.refresh_token = CredentialEncryptionService().encrypt(token)

    def get_refresh_token(self) -> str:
        return CredentialEncryptionService().decrypt(self.refresh_token)

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at <= timezone.now())


class BrokerConnectionLog(models.Model):
    broker_account = models.ForeignKey(BrokerAccount, on_delete=models.CASCADE, related_name="connection_logs")
    status = models.CharField(max_length=50)
    latency = models.FloatField(null=True, blank=True)
    event = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["broker_account", "-created_at"]), models.Index(fields=["event"])]


class BrokerPermission(models.Model):
    broker = models.ForeignKey(Broker, on_delete=models.CASCADE, related_name="permissions")
    permission = models.CharField(max_length=80)
    enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = [("broker", "permission")]
