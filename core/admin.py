from django.contrib import admin
from django.contrib.auth.models import User
from core.models import (
    UserProfile, Subscription, PasswordResetToken, BotSettings,
    Invoice, Payment, ReferralReward, AuditLog, EncryptedCredential
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'email_verified', 'timezone', 'created_at']
    list_filter = ['email_verified', 'two_factor_enabled', 'created_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'plan', 'is_active', 'created_at']
    list_filter = ['plan', 'is_active', 'created_at']
    search_fields = ['user__username']
    readonly_fields = ['created_at', 'renewed_at']


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'used', 'created_at', 'expires_at']
    list_filter = ['used', 'created_at']
    search_fields = ['user__username']
    readonly_fields = ['created_at']


@admin.register(BotSettings)
class BotSettingsAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_enabled', 'status', 'default_strategy', 'is_paper_trading']
    list_filter = ['is_enabled', 'status', 'is_paper_trading']
    search_fields = ['user__username']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['user', 'external_id', 'amount_cents', 'currency', 'paid', 'created_at']
    list_filter = ['paid', 'currency', 'created_at']
    search_fields = ['user__username', 'external_id']
    readonly_fields = ['created_at']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['user', 'external_id', 'amount_cents', 'currency', 'status', 'created_at']
    list_filter = ['status', 'currency', 'created_at']
    search_fields = ['user__username', 'external_id']
    readonly_fields = ['created_at']


@admin.register(ReferralReward)
class ReferralRewardAdmin(admin.ModelAdmin):
    list_display = ['referrer', 'referee', 'amount_credits', 'awarded_at']
    list_filter = ['awarded_at']
    search_fields = ['referrer__username', 'referee__username']
    readonly_fields = ['awarded_at']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'path', 'method', 'status_code', 'created_at']
    list_filter = ['method', 'status_code', 'created_at']
    search_fields = ['user__username', 'path']
    readonly_fields = ['created_at', 'request_body', 'response_body', 'error']


@admin.register(EncryptedCredential)
class EncryptedCredentialAdmin(admin.ModelAdmin):
    list_display = ['user', 'service_name', 'credential_type', 'updated_at']
    list_filter = ['service_name', 'credential_type', 'updated_at']
    search_fields = ['user__username', 'service_name']
    readonly_fields = ['created_at', 'updated_at']

