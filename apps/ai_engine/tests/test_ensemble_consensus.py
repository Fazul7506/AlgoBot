import unittest

from trading.ai.ensemble import EnsemblePredictor


class EnsembleConsensusTests(unittest.TestCase):
    def test_agreement_can_buy(self):
        result = EnsemblePredictor.consensus([
            {"model": "rf", "probability": 0.90, "weight": 1},
            {"model": "xgb", "probability": 0.88, "weight": 1},
            {"model": "lgb", "probability": 0.91, "weight": 1},
        ], min_confidence=0.65)
        self.assertEqual(result["decision"], "BUY")
        self.assertGreater(result["confidence"], 0.65)
        self.assertEqual(result["models_used"], 3)

    def test_conflict_abstains(self):
        result = EnsemblePredictor.consensus([
            {"model": "rf", "probability": 0.95, "weight": 1},
            {"model": "xgb", "probability": 0.05, "weight": 1},
            {"model": "lgb", "probability": 0.50, "weight": 1},
        ], min_confidence=0.65)
        self.assertEqual(result["decision"], "AVOID")

    def test_weights_change_consensus(self):
        result = EnsemblePredictor.consensus([
            {"model": "rf", "probability": 0.90, "weight": 3},
            {"model": "xgb", "probability": 0.20, "weight": 1},
        ], min_confidence=0.65)
        self.assertEqual(result["decision"], "BUY")
        self.assertGreater(result["probability"], 0.70)


if __name__ == "__main__":
    unittest.main()
