"""Regression tests for account-scoped market API broker gating."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from core.models import UserProfile
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.market_data import api as market_api


class AccountScopedMarketBrokerGateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="market-api-gate-user",
            email="market-api-gate@example.test",
            password="Test-password-123!secure",
        )
        UserProfile.objects.update_or_create(user=self.user, defaults={"email_verified": True, "email_verified_at": timezone.now()})
        self.factory = APIRequestFactory()

    @patch("core.broker_onboarding.has_authorized_broker_connection", return_value=False)
    def test_account_scoped_market_endpoints_deny_users_without_eligible_broker(self, _gate):
        requests = (
            (market_api.markets, self.factory.get("/api/markets/"), ()),
            (market_api.symbols, self.factory.get("/api/symbols/"), ()),
            (
                market_api.symbol_detail,
                self.factory.get("/api/symbols/R_100/"),
                ("R_100",),
            ),
            (market_api.sync_symbols, self.factory.post("/api/symbols/sync/", {}, format="json"), ()),
        )
        for view, request, args in requests:
            with self.subTest(view=view.__name__):
                force_authenticate(request, user=self.user)
                response = view(request, *args)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.data["code"], "broker_setup_required")
