from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.brokers.models import Broker, BrokerAccount
from core.dashboard_api import DashboardViewSet


class DashboardAccountOverviewTests(TestCase):
    def test_account_overview_uses_broker_account_relation(self):
        user = get_user_model().objects.create_user(
            username="dashboard-regression",
            email="dashboard-regression@example.com",
            password="test-password",
        )
        broker = Broker.objects.create(
            name="Deriv",
            broker_type="deriv",
            status="active",
        )
        account = BrokerAccount.objects.create(
            user=user,
            broker=broker,
            account_id="DASHBOARD-REGRESSION",
            status="active",
            currency="USD",
            balance="100.00",
            equity="100.00",
        )

        request = APIRequestFactory().get("/api/dashboard/account_overview/")
        force_authenticate(request, user=user)
        response = DashboardViewSet.as_view({"get": "account_overview"})(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["account"]["account_id"], account.account_id)
        self.assertEqual(response.data["data"]["account"]["currency"], "USD")
        self.assertEqual(response.data["data"]["trading_stats"]["total_trades"], 0)
