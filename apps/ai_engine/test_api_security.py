from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Prediction, TrainingJob


class AIAPISecurityTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user_a = user_model.objects.create_user(username="ai-user-a", password="test-password-a")
        self.user_b = user_model.objects.create_user(username="ai-user-b", password="test-password-b")
        self.staff = user_model.objects.create_user(username="ai-staff", password="test-password-staff", is_staff=True)
        Prediction.objects.create(user=self.user_a, symbol="frxEURUSD", timeframe="M1", prediction="BUY", probability=0.8, confidence=80)
        Prediction.objects.create(user=self.user_b, symbol="frxGBPUSD", timeframe="M1", prediction="SELL", probability=0.7, confidence=70)
        TrainingJob.objects.create(user=self.user_a, status="completed")
        TrainingJob.objects.create(user=self.user_b, status="completed")
        self.client = APIClient()

    def test_predictions_are_tenant_scoped(self):
        self.client.force_authenticate(self.user_a)
        response = self.client.get("/api/ai/predictions/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["symbol"], "frxEURUSD")

    def test_training_jobs_are_tenant_scoped_and_read_only(self):
        self.client.force_authenticate(self.user_a)
        response = self.client.get("/api/ai/training-jobs/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(self.client.post("/api/ai/training-jobs/", {}).status_code, 405)

    def test_model_governance_requires_staff(self):
        self.client.force_authenticate(self.user_a)
        self.assertEqual(self.client.get("/api/ai/governance/").status_code, 403)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/ai/governance/").status_code, 200)
