from rest_framework import status
from rest_framework.test import APITestCase


class AIPredictAuthenticationTests(APITestCase):
    def test_api_predict_rejects_anonymous_before_user_scoped_orm_queries(self):
        response = self.client.post(
            "/api/ai/predict/",
            {"symbol": "1HZ100V", "timeframe": "M1"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data.get("detail"), "Authentication credentials are required for AI analysis.")
