from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from core.models import UserProfile


User = get_user_model()


class BrokerOnboardingMiddlewareTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="middleware-user",
            email="middleware@example.test",
            password="Test-password-123!secure",
        )
        UserProfile.objects.create(user=self.user, email_verified=True, email_verified_at=timezone.now())
        self.client.force_login(self.user)

    @patch("core.broker_onboarding.has_authorized_broker_connection", return_value=False)
    def test_authenticated_workspace_pages_redirect_to_broker_setup(self, _gate):
        response = self.client.get(reverse("markets_page"))
        self.assertRedirects(
            response,
            reverse("broker_marketplace_page"),
            fetch_redirect_response=False,
        )

    @patch("core.broker_onboarding.has_authorized_broker_connection", return_value=False)
    def test_authenticated_api_requests_are_denied_without_broker(self, _gate):
        response = self.client.get("/api/orders/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "broker_setup_required")
        self.assertEqual(
            response.json()["next_url"],
            reverse("broker_marketplace_page"),
        )

    @patch("core.broker_onboarding.has_authorized_broker_connection", return_value=False)
    def test_broker_management_remains_available_to_complete_onboarding(self, _gate):
        response = self.client.get(reverse("broker_marketplace_page"))
        self.assertEqual(response.status_code, 200)
