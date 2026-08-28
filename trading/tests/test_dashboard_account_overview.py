from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.brokers.models import Broker, BrokerAccount


class DashboardAccountOverviewTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("dashboard-owner", "dashboard@example.com", "pass")
        self.broker = Broker.objects.create(name="Dashboard Deriv", broker_type="deriv", status="active")
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="VRTC-DASHBOARD",
            currency="USD",
            balance=Decimal("42.50"),
            equity=Decimal("43.25"),
            is_preferred=True,
            status="active",
        )
        self.client.force_authenticate(self.user)

    def test_account_overview_uses_the_canonical_connected_account(self):
        response = self.client.get(reverse("dashboard-account-overview"))

        self.assertEqual(response.status_code, 200)
        account = response.data["data"]["account"]
        self.assertEqual(account["account_id"], self.account.account_id)
        self.assertEqual(account["broker"], self.broker.name)
        self.assertEqual(Decimal(str(account["balance"])), Decimal("42.50000000"))

    def test_live_account_overview_never_exposes_simulation_metrics(self):
        response = self.client.get(reverse("dashboard-account-overview"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("paper_trading", response.data["data"])
