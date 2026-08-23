from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from trading.models import PortfolioSnapshot, Trade


class AnalyticsSmokeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="analytics-smoke", password="test-pass-123")

    def test_dashboard_renders_with_real_models(self):
        PortfolioSnapshot.objects.create(user=self.user, balance=1000, equity=1005)
        self.client.force_login(self.user)
        response = self.client.get(reverse("analytics-dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trading Analytics")

    def test_export_is_user_scoped(self):
        Trade.objects.create(user=self.user, symbol="R_75", contract_type="CALL", entry_price=100, stake=10)
        other = get_user_model().objects.create_user(username="analytics-other", password="test-pass-123")
        Trade.objects.create(user=other, symbol="R_100", contract_type="PUT", entry_price=100, stake=20)
        self.client.force_login(self.user)
        response = self.client.get(reverse("analytics-export"))
        body = response.content.decode()
        self.assertIn("R_75", body)
        self.assertNotIn("R_100", body)
