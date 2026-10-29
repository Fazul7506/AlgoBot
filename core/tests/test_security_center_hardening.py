from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.developer.models import APIKey
from apps.observability.models import AuditEvent


class SecurityCenterHardeningTests(TestCase):
    def test_expired_active_api_keys_are_not_counted_as_usable(self):
        user = get_user_model().objects.create_user(username="security-center-test", password="test-password")
        APIKey.objects.create(
            user=user,
            name="Expired key",
            key="expired-security-center-key",
            secret="secret",
            status="active",
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        APIKey.objects.create(
            user=user,
            name="Usable key",
            key="usable-security-center-key",
            secret="secret",
            status="active",
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(user)
        response = self.client.get("/operations/security/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["keys_count"], 1)
        checks = dict(response.context["checks"])
        self.assertNotIn("Developer key expiry", checks)
        self.assertNotIn("Broker connection", checks)
        self.assertIn("Email verification", checks)
        self.assertIn("Two-factor authentication", checks)

    def test_security_alerts_are_derived_only_from_real_user_scoped_failed_auth_events(self):
        user = get_user_model().objects.create_user(username="security-alert-owner", password="test-password")
        other_user = get_user_model().objects.create_user(username="security-alert-other", password="test-password")
        AuditEvent.objects.create(actor_id=user.pk, action="login_failed", resource_type="Authentication", outcome="failed", metadata={"method": "password"})
        AuditEvent.objects.create(actor_id=other_user.pk, action="login_failed", resource_type="Authentication", outcome="failed", metadata={"method": "password"})
        self.client.force_login(user)
        response = self.client.get("/operations/security/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Security alerts")
        self.assertContains(response, "login_failed")
        self.assertEqual(len(response.context["security_alerts"]), 1)
        self.assertEqual(response.context["security_alerts"][0].action, "login_failed")

    def test_security_center_renders_responsive_dashboard_and_real_activity_context(self):
        user = get_user_model().objects.create_user(username="security-dashboard-test", password="test-password")
        self.client.force_login(user)
        response = self.client.get("/operations/security/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/security_center.html")
        self.assertContains(response, "security_center.css")
        self.assertContains(response, "Two-factor authentication")
        self.assertContains(response, "Password management")
        self.assertContains(response, "Email verification")
        self.assertNotContains(response, "Login activity")
        self.assertNotContains(response, "security-events-table")
        self.assertNotContains(response, "Protection checks")
        self.assertEqual(response.context["security_events"], [])
        self.assertEqual(response.context["login_events"], [])
        self.assertIn(response.context["current_device"], ("Mobile browser", "Desktop or tablet browser"))
