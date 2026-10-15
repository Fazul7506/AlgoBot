from django.contrib.auth import get_user_model
from django.test import TestCase
from unittest.mock import patch
from django.urls import reverse


@patch("core.broker_onboarding.has_authorized_broker_connection", return_value=True)
@patch("core.broker_onboarding.has_verified_account_email", return_value=True)
class OrdersTemplateContractTests(TestCase):
    def test_orders_start_from_broker_connection_state(self):
        user = get_user_model().objects.create_user("orders-owner", "orders@example.com", "pass")
        self.client.force_login(user)
        response = self.client.get(reverse("orders_page"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Broker execution", content)
        self.assertIn("Connect a broker", content)
        self.assertNotIn("25000", content)
        self.assertNotIn("12345", content)
