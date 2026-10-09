from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.developer.models import APIKey


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
        self.assertFalse(checks["Developer key expiry"])
        self.assertFalse(checks["Broker connection"])
