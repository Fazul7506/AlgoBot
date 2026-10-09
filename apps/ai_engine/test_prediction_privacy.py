from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai_engine.models import AIModel, FeatureVector, Prediction


class AIPredictionPrivacyTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="ai-owner", password="test-password")
        self.other = User.objects.create_user(username="ai-other", password="test-password")

    def test_explainability_uses_only_the_authenticated_users_prediction_features(self):
        Prediction.objects.create(
            user=self.user, symbol="R_100", timeframe="M1", prediction="AVOID",
            payload={"feature_values": {"own_drawdown": 0.1, "own_volatility": 0.2}},
        )
        Prediction.objects.create(
            user=self.other, symbol="R_100", timeframe="M1", prediction="BUY",
            payload={"feature_values": {"foreign_account_balance": 99999.0}},
        )
        self.client.force_login(self.user)
        response = self.client.get("/api/ai/explain/?symbol=R_100&timeframe=M1")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("own_drawdown", body)
        self.assertNotIn("foreign_account_balance", body)

    def test_feature_vectors_are_staff_only(self):
        FeatureVector.objects.create(
            symbol="R_100", timeframe="M1", features={"private_risk": 0.75}, feature_hash="ai-private-feature-hash"
        )
        self.client.force_login(self.user)
        response = self.client.get("/api/ai/features/")
        self.assertEqual(response.status_code, 403)

    def test_public_model_registry_does_not_expose_internal_metadata(self):
        AIModel.objects.create(
            name="Public summary model",
            version="1.0.0",
            algorithm="random_forest",
            status="experimental",
            metadata={"training_path": "/private/training/dataset", "internal_marker": "private-model-config"},
        )
        self.client.force_login(self.user)
        response = self.client.get("/api/ai/models/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Public summary model", body)
        self.assertNotIn("private-model-config", body)
        self.assertNotIn("/private/training/dataset", body)

    def test_predict_endpoint_rejects_non_object_payload(self):
        self.client.force_login(self.user)
        response = self.client.post("/api/ai/predict/", data=["R_100"], content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "AI_CONTEXT_INVALID")
