from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection


class DashboardTemplateContractTests(TestCase):
    def test_authenticated_dashboard_does_not_embed_trading_values(self):
        user = get_user_model().objects.create_user("dashboard-owner", "dashboard@example.com", "pass")
        self.client.force_login(user)
        broker = Broker.objects.create(name="Deriv Dashboard Test", broker_type="deriv", status="active")
        account = BrokerAccount.objects.create(
            user=user,
            broker=broker,
            account_id="TEST-DASHBOARD-001",
            status="active",
            token_status="active",
        )
        account.set_access_token("test-dashboard-token")
        account.save(update_fields=["access_token"])
        BrokerConnection.objects.create(broker=broker, broker_account=account, status="connected")
        response = self.client.get(reverse("dashboard_page"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Broker-backed dashboard", content)
        self.assertIn("Unavailable", content)
        self.assertNotIn("25000", content)
        self.assertNotIn("12345", content)
    def test_authenticated_user_without_verified_broker_is_redirected_to_setup(self):
        user = get_user_model().objects.create_user(
            "dashboard-needs-broker", "needs-broker@example.com", "pass"
        )
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard_page"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/brokers/marketplace/")

