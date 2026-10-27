from rest_framework import status
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken


class AIPredictAuthenticationTests(APITestCase):
    def test_api_predict_rejects_anonymous_before_user_scoped_orm_queries(self):
        response = self.client.post(
            "/api/ai/predict/",
            {"symbol": "1HZ100V", "timeframe": "M1"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data.get("detail"), "Authentication credentials were not provided.")
        self.assertEqual(response.data.get("code"), "not_authenticated")

    def test_predict_accepts_valid_bearer_jwt_without_session_csrf_cookie(self):
        user = get_user_model().objects.create_user(
            username="ai-bearer-csrf-test",
            email="ai-bearer-csrf@example.test",
            password="test-password",
        )
        access = str(RefreshToken.for_user(user).access_token)
        client = APIClient(enforce_csrf_checks=True)
        response = client.post(
            "/api/ai/predict/",
            {"symbol": "1HZ100V", "timeframe": "M1"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertNotIn("CSRF", str(response.data))
