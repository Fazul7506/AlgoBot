from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class MarketWatchContractTests(TestCase):
    def test_market_page_starts_without_fabricated_quotes(self):
        user = get_user_model().objects.create_user("market-owner", "market@example.com", "pass")
        self.client.force_login(user)
        response = self.client.get(reverse("markets_page"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Broker market-data engine", content)
        self.assertIn("Connect a broker", content)
        self.assertNotIn("105000", content)
        self.assertNotIn("1.17", content)
