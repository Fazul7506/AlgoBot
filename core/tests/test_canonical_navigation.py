"""Regression coverage for canonical workspace and API ownership."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import resolve, reverse


class CanonicalNavigationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="navigation-regression-user",
            email="navigation-regression@example.invalid",
            password="test-password-123",
        )
        self.client.force_login(self.user)

    def test_analysis_is_the_canonical_research_destination(self):
        response = self.client.get(reverse("analysis_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Analysis | AlgoBot")

    def test_trading_api_resources_have_single_canonical_owner(self):
        expected = {
            "/api/brokers/accounts/": "apps.brokers.views",
            "/api/orders/": "apps.execution.views",
            "/api/positions/open/": "apps.execution.views",
        }
        for path, module in expected.items():
            match = resolve(path)
            callback_class = getattr(match.func, "cls", None)
            self.assertIsNotNone(callback_class, path)
            self.assertEqual(callback_class.__module__, module, path)
