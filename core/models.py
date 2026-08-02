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
    
    # Email verification
    email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=255, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    
    # Account settings
    two_factor_enabled = models.BooleanField(default=False)
    notifications_enabled = models.BooleanField(default=True)
    email_notifications_enabled = models.BooleanField(default=True)
    telegram_notifications_enabled = models.BooleanField(default=False)
    telegram_chat_id = models.CharField(max_length=50, blank=True)
    telegram_username = models.CharField(max_length=100, blank=True)
    telegram_connected_at = models.DateTimeField(null=True, blank=True)
    brevo_api_key = models.CharField(max_length=255, blank=True)
    brevo_sender_email = models.EmailField(blank=True)
    # Referral and billing
    referral_code = models.CharField(max_length=32, blank=True, unique=True, null=True)
    referred_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='referrals')
    referral_credits = models.FloatField(default=0.0)
    
    # Profile metadata
    avatar_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} Profile"


class Subscription(models.Model):
    """Subscription plans placeholder for future monetization"""
    
    PLAN_CHOICES = [
        ('FREE', 'Free'),
        ('BASIC', 'Basic'),
        ('PRO', 'Professional'),
        ('ENTERPRISE', 'Enterprise'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription')
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='FREE')
    
    # Plan limits
    max_strategies = models.IntegerField(default=1)
    max_concurrent_trades = models.IntegerField(default=5)
    api_calls_per_day = models.IntegerField(default=1000)
    
    # Billing
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
    
    # Bot status
    is_enabled = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IDLE')
    
    # Trading parameters
    default_strategy = models.CharField(max_length=100, default='trend')
    max_daily_loss_pct = models.FloatField(default=0.05)
    risk_per_trade_pct = models.FloatField(default=0.01)
    
    # Risk controls
    max_concurrent_trades = models.IntegerField(default=5)
    min_win_rate = models.FloatField(default=0.50)
    
    # Paper trading
    is_paper_trading = models.BooleanField(default=True)
    paper_balance = models.FloatField(default=10000.0)

    # Notification preferences
    email_notifications_enabled = models.BooleanField(default=True)
    telegram_notifications_enabled = models.BooleanField(default=False)
    telegram_chat_id = models.CharField(max_length=50, blank=True)
    telegram_username = models.CharField(max_length=100, blank=True)
    brevo_api_key = models.CharField(max_length=255, blank=True)
    brevo_sender_email = models.EmailField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"Bot settings for {self.user.username}"


class Invoice(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='invoices')
    external_id = models.CharField(max_length=255, blank=True)
    amount_cents = models.IntegerField()
    currency = models.CharField(max_length=10, default='usd')
    paid = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Invoice {self.external_id or self.id} - {self.user.username}"


class Payment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    external_id = models.CharField(max_length=255, blank=True)
    amount_cents = models.IntegerField()
    currency = models.CharField(max_length=10, default='usd')
    status = models.CharField(max_length=50, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment {self.external_id or self.id} - {self.user.username}"


class ReferralReward(models.Model):
    referrer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referrer_rewards')
    referee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referee_rewards')
    amount_credits = models.FloatField(default=0.0)
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-awarded_at']

    def __str__(self):
        return f"Referral {self.referrer.username} -> {self.referee.username}: {self.amount_credits}"


class AuditLog(models.Model):
    """Audit log entry for HTTP requests and critical system events."""

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    path = models.CharField(max_length=500)
    method = models.CharField(max_length=10)
    status_code = models.IntegerField(default=200)
    ip_address = models.CharField(max_length=50, blank=True)
    query_params = models.JSONField(default=dict, blank=True)
    request_body = models.TextField(blank=True)
    response_body = models.TextField(blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['path', '-created_at']),
            models.Index(fields=['status_code', '-created_at']),
        ]

    def __str__(self):
        return f"AuditLog {self.path} {self.method} {self.status_code}"


class EncryptedCredential(models.Model):
    """Secure storage for encrypted third-party credentials."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='encrypted_credentials')
    service_name = models.CharField(max_length=100)
    credential_type = models.CharField(max_length=100, default='api_key')
    encrypted_value = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        unique_together = ('user', 'service_name', 'credential_type')

    def __str__(self):
        return f"EncryptedCredential {self.user.username} {self.service_name} {self.credential_type}"

    def set_value(self, raw_value):
        from core.services.encryption_service import CredentialEncryptionService
        self.encrypted_value = CredentialEncryptionService().encrypt(raw_value)

    def get_value(self):
        from core.services.encryption_service import CredentialEncryptionService
        if not self.encrypted_value:
            return ''
        decrypted = CredentialEncryptionService().decrypt(self.encrypted_value)
        return decrypted if decrypted is not None else ''
