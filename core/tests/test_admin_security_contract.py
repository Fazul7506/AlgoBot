from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase


class AdminSecurityContractTests(TestCase):
    def test_admin_requires_staff(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_can_reach_admin_index(self):
        user = get_user_model().objects.create_superuser(
            username="admin-contract",
            email="admin-contract@example.com",
            password="safe-test-password-123",
        )
        self.client.force_login(user)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)

    def test_sensitive_credential_fields_are_not_admin_editable(self):
        from core.models import BotSettings, EncryptedCredential, PasswordResetToken, UserProfile
        from apps.brokers.models import BrokerAccount

        profile_admin = admin.site._registry[UserProfile]
        self.assertTrue({"email_verification_token", "telegram_chat_id", "telegram_username", "brevo_api_key"}.issubset(set(profile_admin.exclude)))

        bot_admin = admin.site._registry[BotSettings]
        self.assertTrue({"telegram_chat_id", "telegram_username", "brevo_api_key"}.issubset(set(bot_admin.exclude)))

        credential_admin = admin.site._registry[EncryptedCredential]
        self.assertIn("encrypted_value", credential_admin.exclude)
        self.assertFalse(credential_admin.has_add_permission(None))
        self.assertFalse(credential_admin.has_change_permission(None))
        self.assertFalse(credential_admin.has_delete_permission(None))

        broker_admin = admin.site._registry[BrokerAccount]
        self.assertTrue({"credentials", "access_token", "refresh_token"}.issubset(set(broker_admin.exclude)))
        self.assertFalse(broker_admin.has_add_permission(None))
        self.assertFalse(broker_admin.has_change_permission(None))
        self.assertFalse(broker_admin.has_delete_permission(None))

        reset_admin = admin.site._registry[PasswordResetToken]
        self.assertIn("token", reset_admin.readonly_fields)
        self.assertFalse(reset_admin.has_add_permission(None))
        self.assertFalse(reset_admin.has_change_permission(None))
        self.assertFalse(reset_admin.has_delete_permission(None))

    def test_runtime_records_are_read_only_in_admin(self):
        from apps.execution.models import ExecutionLog, ExecutionQueue, Order, ReconciliationEvent
        from apps.monitoring.models import AuditLog, LogEntry, SystemHealth

        for model in (Order, ExecutionLog, ExecutionQueue, ReconciliationEvent, AuditLog, LogEntry, SystemHealth):
            model_admin = admin.site._registry[model]
            self.assertFalse(model_admin.has_add_permission(None), model.__name__)
            self.assertFalse(model_admin.has_change_permission(None), model.__name__)
            self.assertFalse(model_admin.has_delete_permission(None), model.__name__)
