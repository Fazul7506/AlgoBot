from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.developer.models import APIKey


class SecurityCenterContractTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="security-owner", password="test-password"
        )
        self.client.force_login(self.user)

    def _key(self, user, name, *, expires_at=None, status="active"):
        return APIKey.objects.create(
            user=user,
            name=name,
            key=f"test-key-{user.pk}-{name}",
            secret="test-secret",
            expires_at=expires_at,
            status=status,
        )

    def test_security_center_counts_only_unexpired_active_keys_for_current_user(self):
        other_user = get_user_model().objects.create_user(
            username="other-security-owner", password="test-password"
        )
        self._key(self.user, "valid", expires_at=timezone.now() + timedelta(days=1))
        self._key(self.user, "expired", expires_at=timezone.now() - timedelta(seconds=1))
        self._key(other_user, "other-valid", expires_at=timezone.now() + timedelta(days=1))
        self._key(self.user, "revoked", status="revoked")

        response = self.client.get(reverse("security_center"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["keys_count"], 1)
        self.assertContains(response, "active developer key")

    def test_expired_active_key_is_reported_as_needing_attention(self):
        self._key(self.user, "expired", expires_at=timezone.now() - timedelta(seconds=1))

        response = self.client.get(reverse("security_center"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["keys_count"], 0)
        self.assertContains(response, "Developer key expiry")
        self.assertContains(response, "Needs attention")
