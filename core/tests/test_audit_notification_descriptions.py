from django.test import SimpleTestCase

from core.middleware.audit_middleware import AuditMiddleware


class AuditNotificationDescriptionTests(SimpleTestCase):
    def test_two_factor_action_has_a_specific_explanation(self):
        title, message, category, priority = AuditMiddleware._notification_details(
            "/api/account/security/two-factor/disable/", "POST", "account"
        )
        self.assertEqual(title, "Two-factor authentication disabled")
        self.assertIn("turned off", message)
        self.assertEqual(category, "security")
        self.assertEqual(priority, "critical")

    def test_trusted_device_action_is_described_without_device_payload(self):
        title, message, category, priority = AuditMiddleware._notification_details(
            "/api/security/trusted-devices/register/", "POST", "security"
        )
        self.assertEqual(title, "Trusted device added")
        self.assertIn("trusted devices", message)
        self.assertNotIn("password", message.lower())
        self.assertEqual(category, "security")
        self.assertEqual(priority, "critical")

    def test_generic_module_action_uses_route_context_not_a_blanket_success_message(self):
        title, message, category, priority = AuditMiddleware._notification_details(
            "/api/strategies/activate/", "POST", "strategies"
        )
        self.assertIn("Activate", title)
        self.assertIn("activate", message.lower())
        self.assertNotIn("action was completed successfully", message.lower())
        self.assertEqual(category, "strategies")
        self.assertEqual(priority, "info")

    def test_notification_copy_never_contains_request_identifiers_or_values(self):
        _, message, _, _ = AuditMiddleware._notification_details(
            "/api/brokers/accounts/123456/disconnect/", "POST", "brokers"
        )
        self.assertNotIn("123456", message)
        self.assertNotIn("token", message.lower())
