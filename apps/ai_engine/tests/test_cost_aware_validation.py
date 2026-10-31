import unittest

import numpy as np

from apps.ai_engine.validation import _trading_metrics


class DirectionalValidationTests(unittest.TestCase):
    def test_metrics_use_observed_gross_returns(self):
        y = np.array([1, 0], dtype=np.int8)
        predictions = np.array([1, 0], dtype=np.int8)
        returns = np.array([0.002, -0.001], dtype=float)
        metrics = _trading_metrics(y, predictions, returns)
        self.assertAlmostEqual(metrics["total_return"], 0.003)
        self.assertAlmostEqual(metrics["expectancy"], 0.0015)


if __name__ == "__main__":
    unittest.main()
