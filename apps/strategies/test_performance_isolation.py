from django.contrib.auth import get_user_model
from django.test import TestCase
from unittest.mock import patch
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.strategies.views import StrategyViewSet


@patch("core.permissions.has_authorized_broker_connection", new=lambda user: True)
@patch("core.permissions.has_verified_account_email", new=lambda user: True)
@patch("core.permissions.has_authorized_broker_connection", return_value=True)
@patch("core.permissions.has_verified_account_email", return_value=True)
@patch("core.broker_onboarding.has_authorized_broker_connection", return_value=True)
@patch("core.broker_onboarding.has_verified_account_email", return_value=True)
class StrategyPerformanceIsolationTests(TestCase):
    def test_global_strategy_performance_is_not_presented_as_personal_pnl(self):
        user = get_user_model().objects.create_user(username="strategy-user", password="test-password")
        request = APIRequestFactory().get("/api/strategies/performance/")
        force_authenticate(request, user=user)
        response = StrategyViewSet.as_view({"get": "performance"})(request)
        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.data["code"], "ACCOUNT_PERFORMANCE_UNAVAILABLE")
        self.assertNotIn("win_rate", response.data)
        self.assertNotIn("net_profit", response.data)
