"""Core models for user profiles, subscriptions, and bot settings."""
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid


class UserProfile(models.Model):
    """Extended user profile with trading-specific settings"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='trading_profile')
    bio = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, blank=True)
    timezone = models.CharField(max_length=100, default='UTC')
    email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=255, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    two_factor_enabled = models.BooleanField(default=False)
    notifications_enabled = models.BooleanField(default=True)
    email_notifications_enabled = models.BooleanField(default=True)
    telegram_notifications_enabled = models.BooleanField(default=False)
    telegram_chat_id = models.CharField(max_length=50, blank=True)
    telegram_username = models.CharField(max_length=100, blank=True)
    telegram_connected_at = models.DateTimeField(null=True, blank=True)
    brevo_api_key = models.CharField(max_length=255, blank=True)
    brevo_sender_email = models.EmailField(blank=True)
    referral_code = models.CharField(max_length=32, blank=True, unique=True, null=True)
    referred_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='referrals')
    referral_credits = models.FloatField(default=0.0)
    avatar_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} Profile"


class Subscription(models.Model):
    """Subscription plans for monetization"""
    PLAN_CHOICES = [
        ('FREE', 'Free'),
        ('BASIC', 'Basic'),
        ('PRO', 'Professional'),
        ('ENTERPRISE', 'Enterprise'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription')
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='FREE')
    max_strategies = models.IntegerField(default=1)
    max_concurrent_trades = models.IntegerField(default=5)
    api_calls_per_day = models.IntegerField(default=1000)
    stripe_price_id = models.CharField(max_length=255, blank=True)
    price_cents = models.IntegerField(default=0)
    currency = models.CharField(max_length=10, default='usd')
    recurring = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    renewed_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.plan}"


class PasswordResetToken(models.Model):
    """Secure password reset tokens"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reset_tokens')
    token = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def is_valid(self):
        return not self.used and timezone.now() < self.expires_at

    def __str__(self):
        return f"Reset token for {self.user.username}"


class BotSettings(models.Model):
    """Per-user bot configuration and settings"""
    STATUS_CHOICES = [
        ('IDLE', 'Idle'),
        ('RUNNING', 'Running'),
        ('PAUSED', 'Paused'),
        ('ERROR', 'Error'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='bot_settings')
    is_enabled = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IDLE')
    default_strategy = models.CharField(max_length=100, default='trend')
    max_daily_loss_pct = models.FloatField(default=0.05)
    risk_per_trade_pct = models.FloatField(default=0.01)
    max_concurrent_trades = models.IntegerField(default=5)
    min_win_rate = models.FloatField(default=0.50)
    is_paper_trading = models.BooleanField(default=True)
    paper_balance = models.FloatField(default=10000.0)
    email_notifications_enabled = models.BooleanField(default=True)
    telegram_notifications_enabled = models.BooleanField(default=False)
    telegram_chat_id = models.CharField(max_length=50, blank=True)
    telegram_username = models.CharField(max_length=100, blank=True)
    brevo_api_key = models.CharField(max_length=255, blank=True)
    brevo_sender_email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} Bot Settings"


class AuditLog(models.Model):
    """Audit trail for API requests"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='audit_logs')
    path = models.CharField(max_length=500)
    method = models.CharField(max_length=10)
    status_code = models.IntegerField()
    ip_address = models.CharField(max_length=45, blank=True)
    user_agent = models.TextField(blank=True)
    request_body = models.TextField(blank=True)
    response_body = models.TextField(blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', '-created_at'])]

    def __str__(self):
        return f"{self.method} {self.path} - {self.status_code}"


class Invoice(models.Model):
    """Invoice records with provider/checkout metadata."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='invoices')
    external_id = models.CharField(max_length=255, unique=True, db_index=True, null=True, blank=True)
    amount_cents = models.IntegerField()
    currency = models.CharField(max_length=10, default='usd')
    paid = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', '-created_at'])]

    def __str__(self):
        return f"Invoice {self.external_id or self.pk} - ${self.amount_cents/100:.2f}"


class Payment(models.Model):
    """Payment records linked to their invoice."""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    external_id = models.CharField(max_length=255, unique=True, db_index=True, null=True, blank=True)
    amount_cents = models.IntegerField()
    currency = models.CharField(max_length=10, default='usd')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', '-created_at'])]

    def __str__(self):
        return f"Payment {self.external_id or self.pk} - {self.status}"


class ReferralReward(models.Model):
    """Referral reward records"""
    referrer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referral_rewards_given')
    referee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referral_rewards_received')
    amount_credits = models.FloatField()
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-awarded_at']
        unique_together = ('referrer', 'referee')

    def __str__(self):
        return f"{self.referrer.username} -> {self.referee.username}: {self.amount_credits}"


class EncryptedCredential(models.Model):
    """Store encrypted credentials for external services"""
    CREDENTIAL_TYPES = [
        ('API_KEY', 'API Key'),
        ('OAUTH', 'OAuth Token'),
        ('USERNAME_PASSWORD', 'Username/Password'),
        ('CERTIFICATE', 'Certificate'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='encrypted_credentials')
    service_name = models.CharField(max_length=100, db_index=True)
    credential_type = models.CharField(max_length=50, choices=CREDENTIAL_TYPES)
    encrypted_value = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('user', 'service_name')
        indexes = [models.Index(fields=['user', 'service_name'])]

    def __str__(self):
        return f"{self.user.username} - {self.service_name}"
