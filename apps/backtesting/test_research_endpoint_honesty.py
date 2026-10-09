from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.backtesting.api import optimization_start, replay


class BacktestResearchEndpointHonestyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="research-user", password="test-password")
        self.factory = APIRequestFactory()

    def test_optimization_does_not_return_synthetic_parameter_scores(self):
        request = self.factory.post(
            "/api/backtests/optimization/start/",
            {"optimizer": "grid", "space": {"stake": [1, 2]}},
            format="json",
        )
        force_authenticate(request, user=self.user)
        result = optimization_start(request)
        self.assertEqual(result.status_code, 501)
        self.assertEqual(result.data["code"], "OPTIMIZATION_ENGINE_UNAVAILABLE")
        self.assertNotIn("results", result.data)

    def test_replay_does_not_claim_process_local_flags_are_a_real_session(self):
        request = self.factory.get("/api/backtests/replay/")
        force_authenticate(request, user=self.user)
        result = replay(request)
        self.assertEqual(result.status_code, 501)
        self.assertEqual(result.data["code"], "MARKET_REPLAY_UNAVAILABLE")
