import json
"""Regression tests for mandatory broker onboarding in copy trading."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone
from core.models import UserProfile

from apps.copy_trading import views


class CopyTradingBrokerOnboardingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="copy-trading-gate-user",
            email="copy-trading-gate@example.test",
            password="Test-password-123!secure",
        )
        UserProfile.objects.update_or_create(user=self.user, defaults={"email_verified": True, "email_verified_at": timezone.now()})
        self.factory = RequestFactory()

    @patch("core.broker_onboarding.has_authorized_broker_connection", return_value=False)
    def test_every_copy_trading_endpoint_fails_closed_without_eligible_broker(self, _gate):
        endpoints = (
            ("dashboard", "get"),
            ("subscribe", "post"),
            ("pause", "post"),
            ("resume", "post"),
            ("stop", "post"),
            ("risk_settings", "post"),
            ("test_copy", "post"),
        )
        for name, method in endpoints:
            with self.subTest(endpoint=name):
                path = f"/copy-trading/{name}/"
                if method == "post":
                    request = self.factory.post(path, data="{}", content_type="application/json")
                else:
                    request = self.factory.get(path)
                request.user = self.user

                response = getattr(views, name)(request)

                self.assertEqual(response.status_code, 403)
                self.assertEqual(json.loads(response.content)["code"], "broker_setup_required")
