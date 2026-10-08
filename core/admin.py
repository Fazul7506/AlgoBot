"""Django admin configuration for core models."""
from django.contrib import admin
from core.models import (
    UserProfile, Subscription, PasswordResetToken, BotSettings,
    Invoice, Payment, PaymentWebhookEvent, ReferralReward, AuditLog, EncryptedCredential
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin for user profiles."""
    list_display = ["user", "email_verified", "timezone", "created_at"]
    list_filter = ["email_verified", "two_factor_enabled", "created_at"]
    search_fields = ["user__username", "user__email"]
    readonly_fields = [
        "created_at", "updated_at", "email_verification_token",
        "telegram_chat_id", "telegram_username", "brevo_api_key",
    ]


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Provider-managed subscription state is read-only in admin."""
    list_display = ["user", "plan", "is_active", "created_at"]
    list_filter = ["plan", "is_active", "created_at"]
    search_fields = ["user__username"]
    readonly_fields = [
        "created_at", "renewed_at", "plan", "max_strategies",
        "max_concurrent_trades", "api_calls_per_day", "price_cents",
        "currency", "recurring", "expires_at", "is_active", "provider",
        "provider_subscription_id", "cancelled_at", "cancellation_reason",
    ]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    """Reset tokens are runtime-generated secrets and never admin-editable."""
    list_display = ["user", "used", "created_at", "expires_at"]
    list_filter = ["used", "created_at"]
    search_fields = ["user__username"]
    readonly_fields = ["created_at", "expires_at", "used_at", "token"]

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(BotSettings)
class BotSettingsAdmin(admin.ModelAdmin):
    """Admin may inspect bot settings but cannot alter stored credentials."""
    list_display = ["user", "is_enabled", "status", "default_strategy"]
    list_filter = ["is_enabled", "status"]
    search_fields = ["user__username"]
    readonly_fields = [
        "created_at", "updated_at", "telegram_chat_id",
        "telegram_username", "brevo_api_key",
    ]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    """Provider-generated invoices are immutable in admin."""
    list_display = ["user", "external_id", "amount_cents", "currency", "paid", "created_at"]
    list_filter = ["paid", "currency", "created_at"]
    search_fields = ["user__username", "external_id"]
    readonly_fields = ["created_at", "external_id", "amount_cents", "currency", "paid", "metadata"]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Provider payment records are immutable in admin."""
    list_display = ["user", "external_id", "amount_cents", "currency", "status", "created_at"]
    list_filter = ["status", "currency", "created_at"]
    search_fields = ["user__username", "external_id"]
    readonly_fields = ["created_at", "external_id", "amount_cents", "currency", "status", "invoice", "user"]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(ReferralReward)
class ReferralRewardAdmin(admin.ModelAdmin):
    list_display = ["referrer", "referee", "amount_credits", "awarded_at"]
    list_filter = ["awarded_at"]
    search_fields = ["referrer__username", "referee__username"]
    readonly_fields = ["awarded_at"]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Audit records must remain append-only and tamper-resistant."""
    list_display = ["user", "path", "method", "status_code", "created_at"]
    list_filter = ["method", "status_code", "created_at"]
    search_fields = ["user__username", "path"]
    readonly_fields = [
        "user", "path", "method", "status_code", "ip_address",
        "user_agent", "request_body", "response_body", "error", "created_at",
    ]

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(EncryptedCredential)
class EncryptedCredentialAdmin(admin.ModelAdmin):
    """Credential ciphertext is intentionally never rendered by admin forms."""
    list_display = ["user", "service_name", "credential_type", "updated_at"]
    list_filter = ["service_name", "credential_type", "updated_at"]
    search_fields = ["user__username", "service_name"]
    readonly_fields = ["user", "service_name", "credential_type", "created_at", "updated_at"]
    exclude = ["encrypted_value"]

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(PaymentWebhookEvent)
class PaymentWebhookEventAdmin(admin.ModelAdmin):
    """Webhook receipts are immutable evidence for payment processing."""
    list_display = [
        "provider", "event_key", "external_id", "received_status",
        "processed_status", "received_at", "processed_at", "attempts",
    ]
    list_filter = ["provider", "received_status", "processed_status"]
    search_fields = ["event_key", "external_id", "payload_hash"]
    readonly_fields = [field.name for field in PaymentWebhookEvent._meta.fields]

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
