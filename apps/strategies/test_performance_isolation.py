from django.contrib.auth import get_user_model
from django.test import TestCase
from unittest.mock import patch
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.strategies.views import StrategyViewSet


@patch("core.permissions.has_authorized_broker_connection", new=lambda user: True)
@patch("core.permissions.has_verified_account_email", new=lambda user: True)
@patch("core.permissions.has_authorized_broker_connection", new=lambda user: True)
@patch("core.permissions.has_verified_account_email", new=lambda user: True)
@patch("core.broker_onboarding.has_authorized_broker_connection", new=lambda user: True)
@patch("core.broker_onboarding.has_verified_account_email", new=lambda user: True)
class StrategyPerformanceIsolationTests(TestCase):
    def test_strategy_performance_is_available_without_exposing_global_pnl_as_personal(self):
        user = get_user_model().objects.create_user(username="strategy-user", password="test-password")
        request = APIRequestFactory().get("/api/strategies/performance/")
        force_authenticate(request, user=user)
        response = StrategyViewSet.as_view({"get": "performance"})(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["scope"], "strategy_aggregate")
        self.assertIn("not personal account P&L", response.data["detail"])
        self.assertIsInstance(response.data["results"], list)
        for row in response.data["results"]:
            self.assertEqual(row["scope"], "strategy_aggregate")
            self.assertNotIn("net_profit", row)
