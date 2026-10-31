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

from apps.ai_engine.candlestick_features import FEATURE_NAMES, extract_candlestick_features


class MarketRegimeFeatureTests(unittest.TestCase):
    def test_regime_and_vwap_features_are_in_feature_contract(self):
        candles = []
        for index in range(60):
            close = 100.0 + index * 0.1 + (0.2 if index % 2 else -0.2)
            candles.append({
                "open": close - 0.05,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "volume": 100 + index,
            })
        features = extract_candlestick_features(candles)
        self.assertEqual(len(FEATURE_NAMES), len(features))
        self.assertIn("rolling_volatility_5", features)
        self.assertIn("rolling_volatility_20", features)
        self.assertIn("volatility_regime_ratio", features)
        self.assertIn("vwap_distance", features)
        self.assertEqual(features["volume_available"], 1.0)

    def test_missing_volume_is_explicitly_marked_unavailable(self):
        candles = []
        for index in range(60):
            close = 100.0 + index * 0.1
            candles.append({
                "open": close - 0.05,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
            })
        features = extract_candlestick_features(candles)
        self.assertEqual(features["volume_available"], 0.0)
        self.assertEqual(features["vwap_distance"], 0.0)


if __name__ == "__main__":
    unittest.main()
