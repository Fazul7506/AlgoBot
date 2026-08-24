from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class PortfolioPositionsTemplateContractTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("portfolio-owner", "portfolio@example.com", "pass")
        self.client.force_login(self.user)

    def test_positions_start_without_fabricated_broker_data(self):
        response = self.client.get(reverse("positions_page"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Connect a broker", content)
        self.assertNotIn("25000", content)
        self.assertNotIn("12345", content)

    def test_portfolio_starts_from_broker_connection_state(self):
        response = self.client.get(reverse("portfolio_page"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Portfolio command", content)
        self.assertIn("Connect a broker", content)
