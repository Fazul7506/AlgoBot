from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class DashboardTemplateContractTests(TestCase):
    def test_authenticated_dashboard_does_not_embed_trading_values(self):
        user = get_user_model().objects.create_user("dashboard-owner", "dashboard@example.com", "pass")
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Broker-backed dashboard", content)
        self.assertIn("Unavailable", content)
        self.assertNotIn("25000", content)
        self.assertNotIn("12345", content)
