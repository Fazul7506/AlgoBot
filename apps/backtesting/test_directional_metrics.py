from django.test import SimpleTestCase

from apps.backtesting.tasks import _window_result


class DirectionalBacktestMetricTests(SimpleTestCase):
    def test_directional_unit_scores_are_not_reported_as_financial_returns(self):
        result = _window_result(
            {
                "total_trades": 2,
                "trades": [
                    {"entry_epoch": 11, "exit_epoch": 12, "profit": 1.0, "direction": "long"},
                    {"entry_epoch": 13, "exit_epoch": 14, "profit": -1.0, "direction": "short"},
                ],
            },
            start_epoch=10,
            end_epoch=20,
        )
        self.assertFalse(result["financial_metrics_available"])
        self.assertEqual(result["performance_basis"], "directional_unit_score_no_costs")
        self.assertEqual(result["directional_score"], 0.0)
        self.assertEqual(result["directional_hit_rate"], 50.0)
        self.assertIsNone(result["net_profit"])
        self.assertIsNone(result["total_profit"])
        self.assertIsNone(result["roi"])
        self.assertEqual(result["equity_curve"], [])
        self.assertIsNone(result["trades"][0]["profit"])
