from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class TradeHistoryContractTests(TestCase):
    def test_trade_history_page_starts_from_broker_connection_state(self):
        user = get_user_model().objects.create_user("history-owner", "history@example.com", "pass")
        self.client.force_login(user)
        response = self.client.get(reverse("trade_history_page"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Confirmed execution reports", content)
        self.assertIn("Connect a broker", content)
