import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.observability.models import AuditEvent
from core.models import TrustedDevice


class TrustedDevicesApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="trust-owner", password="Strong-password-123!")
        self.other = get_user_model().objects.create_user(username="trust-other", password="Strong-password-456!")
        self.client.force_login(self.user)

    def test_trusting_browser_requires_current_password_and_stores_only_hash(self):
        url = reverse("trusted-devices-api")
        bad = self.client.post(url, data=json.dumps({"name":"Laptop", "current_password":"wrong"}), content_type="application/json")
        self.assertEqual(bad.status_code, 403)
        self.assertEqual(TrustedDevice.objects.count(), 0)
        good = self.client.post(url, data=json.dumps({"name":"Laptop", "current_password":"Strong-password-123!"}), content_type="application/json")
        self.assertEqual(good.status_code, 200, good.content)
        row = TrustedDevice.objects.get(user=self.user)
        self.assertNotEqual(row.token_hash, good.cookies["algobot_trusted_device"].value)
        self.assertTrue(good.cookies["algobot_trusted_device"]["httponly"])
        self.assertEqual(good.cookies["algobot_trusted_device"]["samesite"], "Lax")

    def test_device_inventory_and_revocation_are_user_scoped(self):
        token = "example-random-token"
        row = TrustedDevice.objects.create(user=self.user, name="Phone", token_hash=__import__("hashlib").sha256(token.encode()).hexdigest())
        other_row = TrustedDevice.objects.create(user=self.other, name="Other", token_hash=__import__("hashlib").sha256(b"other-token").hexdigest())
        response = self.client.get(reverse("trusted-devices-api"))
        self.assertEqual([item["id"] for item in response.json()["devices"]], [row.pk])
        denied = self.client.delete(reverse("trusted-device-detail-api", args=[other_row.pk]))
        self.assertEqual(denied.status_code, 404)
        self.assertIsNone(other_row.revoked_at)
        revoked = self.client.delete(reverse("trusted-device-detail-api", args=[row.pk]))
        self.assertEqual(revoked.status_code, 200)
        row.refresh_from_db()
        self.assertIsNotNone(row.revoked_at)

    def test_security_alert_feed_returns_only_current_users_failed_authentication_events(self):
        AuditEvent.objects.create(actor_id=self.user.pk, action="login_failed", resource_type="Authentication", outcome="failed", metadata={})
        AuditEvent.objects.create(actor_id=self.other.pk, action="login_failed", resource_type="Authentication", outcome="failed", metadata={})
        AuditEvent.objects.create(actor_id=self.user.pk, action="profile_update", resource_type="Profile", outcome="failed", metadata={})
        response = self.client.get(reverse("security-alerts-api"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["alerts"]), 1)
        self.assertEqual(response.json()["alerts"][0]["action"], "login_failed")
