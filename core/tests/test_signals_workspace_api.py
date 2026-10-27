from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.market_data.signals_workspace_api import _outcome_stats


class SignalsWorkspaceAuthenticationTests(TestCase):
    def test_workspace_api_requires_authentication(self):
        response = self.client.get("/api/signals/workspace/")
        self.assertIn(response.status_code, (302, 401, 403))

    def test_invalid_pagination_is_rejected_for_authenticated_user(self):
        user = get_user_model().objects.create_user(username="signals-api-test", password="safe-test-password")
        self.client.force_login(user)
        response = self.client.get("/api/signals/workspace/?page=abc")
        # Account selection happens before pagination validation and can legitimately
        # return 409 when onboarding is incomplete.
        self.assertIn(response.status_code, (400, 409))


class SignalsOutcomeAggregationTests(TestCase):
    def test_outcomes_exclude_open_signals_and_calculate_profit_factor(self):
        stats = _outcome_stats([
            {"metadata": {"outcome": "win", "realized_pnl": "20"}},
            {"metadata": {"outcome": "loss", "realized_pnl": "-10"}},
            {"metadata": {"outcome": "breakeven", "realized_pnl": "0"}},
            {"metadata": {"status": "open", "realized_pnl": "99"}},
        ])
        self.assertEqual(stats["wins"], 1)
        self.assertEqual(stats["losses"], 1)
        self.assertEqual(stats["breakeven"], 1)
        self.assertEqual(stats["completed"], 3)
        self.assertEqual(stats["win_rate"], 33.33)
        self.assertEqual(stats["profit_factor"], "2")
        self.assertEqual(stats["realized_pnl"], "10")

    def test_profit_factor_is_unavailable_when_no_realized_losses_exist(self):
        stats = _outcome_stats([
            {"metadata": {"outcome": "win", "realized_pnl": "12"}},
        ])
        self.assertIsNone(stats["profit_factor"])
