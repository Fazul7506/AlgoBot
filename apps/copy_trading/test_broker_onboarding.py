"""Regression tests for mandatory broker onboarding in copy trading."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.copy_trading import views


class CopyTradingBrokerOnboardingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="copy-trading-gate-user",
            password="Test-password-123!secure",
        )
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
                request = getattr(self.factory, method)(
                    f"/copy-trading/{name}/",
                    data="{}" if method == "post" else None,
                    content_type="application/json",
                )
                request.user = self.user

                response = getattr(views, name)(request)

                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["code"], "broker_setup_required")
