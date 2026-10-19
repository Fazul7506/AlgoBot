from django.contrib.auth import get_user_model
from django.test import TestCase
from unittest.mock import patch
from django.urls import reverse


@patch("core.broker_onboarding.has_authorized_broker_connection", new=lambda user: True)
@patch("core.broker_onboarding.has_verified_account_email", new=lambda user: True)
@patch("core.permissions.has_authorized_broker_connection", new=lambda user: True)
@patch("core.permissions.has_verified_account_email", new=lambda user: True)
@patch("core.broker_onboarding.has_authorized_broker_connection", new=lambda user: True)
@patch("core.broker_onboarding.has_verified_account_email", new=lambda user: True)
class PortfolioPositionsTemplateContractTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("portfolio-owner", "portfolio@example.com", "pass")
        self.client.force_login(self.user)

    def test_positions_start_without_fabricated_broker_data(self):
        response = self.client.get(reverse("positions_page"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Authoritative positions synchronized from the selected broker account.", content)
        self.assertIn("Waiting for broker synchronization.", content)
        self.assertNotIn("25000", content)
        self.assertNotIn("12345", content)

    def test_portfolio_starts_from_broker_connection_state(self):
        response = self.client.get(reverse("portfolio_page"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Portfolio overview", content)
        self.assertIn("Connect a broker", content)
