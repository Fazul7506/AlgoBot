import unittest

import numpy as np

from apps.ai_engine.training_dataset import transaction_cost_rate
from apps.ai_engine.validation import _trading_metrics


class CostAwareValidationTests(unittest.TestCase):
    def test_cost_rate_reads_basis_points_and_caps_unreasonable_values(self):
        from unittest.mock import patch

        with patch.dict("os.environ", {"AI_TRANSACTION_COST_BPS": "12"}):
            self.assertAlmostEqual(transaction_cost_rate(), 0.0012)
        with patch.dict("os.environ", {"AI_TRANSACTION_COST_BPS": "999999"}):
            self.assertEqual(transaction_cost_rate(), 0.05)

    def test_round_trip_cost_is_deducted_from_each_simulated_trade(self):
        y = np.array([1, 0], dtype=np.int8)
        predictions = np.array([1, 0], dtype=np.int8)
        returns = np.array([0.002, -0.001], dtype=float)
        gross = _trading_metrics(y, predictions, returns, 0.0)
        net = _trading_metrics(y, predictions, returns, 0.001)
        self.assertAlmostEqual(net["total_return"], gross["total_return"] - 0.002)
        self.assertLess(net["expectancy"], gross["expectancy"])


if __name__ == "__main__":
    unittest.main()
