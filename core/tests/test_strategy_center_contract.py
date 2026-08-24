from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class StrategyCenterContractTests(TestCase):
    def test_strategy_center_starts_from_broker_connection_state(self):
        user = get_user_model().objects.create_user("strategy-owner", "strategy@example.com", "pass")
        self.client.force_login(user)
        response = self.client.get(reverse("strategies_page"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Broker-aware quant engine", content)
        self.assertIn("Connect a broker", content)
