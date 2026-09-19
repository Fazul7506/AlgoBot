from django.test import SimpleTestCase

from apps.ai_engine.candlestick_features import FEATURE_NAMES
from apps.ai_engine.training_dataset import (
    AI_FEEDBACK_FEATURE_NAMES,
    MODEL_FEATURE_NAMES,
    STRATEGY_FEATURE_NAMES,
)


class AIModelFeatureContractTests(SimpleTestCase):
    def test_training_and_live_inference_share_one_feature_contract(self):
        expected = tuple(
            FEATURE_NAMES
            + tuple(AI_FEEDBACK_FEATURE_NAMES)
            + tuple(STRATEGY_FEATURE_NAMES)
        )
        self.assertEqual(MODEL_FEATURE_NAMES, expected)
        self.assertEqual(len(MODEL_FEATURE_NAMES), len(set(MODEL_FEATURE_NAMES)))
        self.assertIn("strategy_signal_bias", MODEL_FEATURE_NAMES)
        self.assertIn("ai_feedback_accuracy", MODEL_FEATURE_NAMES)
