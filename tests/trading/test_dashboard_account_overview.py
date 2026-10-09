from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.contrib.sessions.middleware import SessionMiddleware
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection, Position
from core.account_context import SESSION_KEY
from apps.execution.models import Order
from core.dashboard_api import DashboardViewSet


class DashboardAccountOverviewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="dashboard-regression",
            email="dashboard-regression@example.com",
            password="test-password",
        )
        self.other_user = get_user_model().objects.create_user(
            username="dashboard-other",
            email="dashboard-other@example.com",
            password="test-password",
        )
        self.broker = Broker.objects.create(
            name="Deriv",
            broker_type="deriv",
            status="active",
        )
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="DASHBOARD-REGRESSION",
            status="active",
            currency="USD",
            balance="100.00",
            equity="100.00",
        )
        self.other_account = BrokerAccount.objects.create(
            user=self.other_user,
            broker=self.broker,
            account_id="DASHBOARD-OTHER",
            status="active",
            currency="USD",
            balance="900.00",
            equity="900.00",
        )
        BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=self.account,
            status="connected",
        )
        BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=self.other_account,
            status="connected",
        )

    def _get(self, action, user=None):
        request = APIRequestFactory().get(f"/api/dashboard/{action}/")
        force_authenticate(request, user=user or self.user)
        return DashboardViewSet.as_view({"get": action})(request)

    def test_account_overview_uses_broker_account_relation(self):
        response = self._get("account_overview")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["account"]["account_id"], self.account.account_id)
        self.assertEqual(response.data["data"]["account"]["currency"], "USD")
        self.assertEqual(response.data["data"]["trading_stats"]["total_trades"], 0)
        self.assertIsNone(response.data["data"]["trading_stats"]["total_pnl"])

    def test_account_overview_uses_real_position_pnl_instead_of_synthetic_zeroes(self):
        Position.objects.create(
            broker=self.broker,
            account=self.account,
            contract_id="TEST-CONTRACT-1",
            symbol="1HZ100V",
            stake="10",
            entry_price="100",
            current_price="103",
            profit="3",
            status="closed",
        )
        response = self._get("account_overview")

        stats = response.data["data"]["trading_stats"]
        self.assertEqual(stats["total_trades"], 1)
        self.assertEqual(stats["wins"], 1)
        self.assertEqual(stats["losses"], 0)
        self.assertEqual(stats["realized_pnl"], Decimal("3"))
        self.assertEqual(stats["total_pnl"], Decimal("3"))
        self.assertEqual(stats["win_rate"], Decimal("100"))

    def test_dashboard_does_not_cross_account_boundary(self):
        Position.objects.create(
            broker=self.broker,
            account=self.account,
            contract_id="TEST-CONTRACT-OWN",
            symbol="OWN",
            stake="10",
            entry_price="100",
            current_price="101",
            profit="1",
            status="closed",
        )
        Position.objects.create(
            broker=self.broker,
            account=self.other_account,
            contract_id="TEST-CONTRACT-OTHER",
            symbol="OTHER",
            stake="10",
            entry_price="100",
            current_price="50",
            profit="-50",
            status="closed",
        )

        response = self._get("account_overview", self.user)
        stats = response.data["data"]["trading_stats"]
        self.assertEqual(stats["total_trades"], 1)
        self.assertEqual(stats["total_pnl"], Decimal("1"))
        self.assertEqual(response.data["data"]["account"]["account_id"], self.account.account_id)

    def test_no_connected_account_is_not_reported_as_zero(self):
        disconnected = get_user_model().objects.create_user(
            username="dashboard-disconnected",
            password="test-password",
        )
        response = self._get("account_overview", disconnected)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "unavailable")
        self.assertIsNone(response.data["data"]["account"])
        self.assertIsNone(response.data["data"]["trading_stats"])

    def test_account_overview_requires_authentication(self):
        request = APIRequestFactory().get("/api/dashboard/account_overview/")
        response = DashboardViewSet.as_view({"get": "account_overview"})(request)
        self.assertIn(response.status_code, (401, 403))

    def test_account_overview_uses_the_server_session_selected_account(self):
        selected = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="DASHBOARD-SESSION-SELECTED",
            status="active",
            currency="EUR",
            balance="250.00",
            equity="250.00",
        )
        BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=selected,
            status="connected",
        )
        request = APIRequestFactory().get("/api/dashboard/account_overview/")
        SessionMiddleware(lambda current_request: None).process_request(request)
        request.session[SESSION_KEY] = selected.pk
        request.session.save()
        force_authenticate(request, user=self.user)
        response = DashboardViewSet.as_view({"get": "account_overview"})(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["account"]["id"], selected.pk)
        self.assertEqual(response.data["data"]["account"]["account_id"], selected.account_id)

    def test_dashboard_trade_history_is_scoped_to_the_server_selected_account(self):
        selected = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="DASHBOARD-ORDER-SELECTED",
            status="active",
            currency="USD",
        )
        BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=selected,
            status="connected",
        )
        Order.objects.create(
            user=self.user,
            broker_account=self.account,
            symbol="OWN-ACCOUNT",
            direction="buy",
            stake="10",
            status="executed",
        )
        Order.objects.create(
            user=self.user,
            broker_account=selected,
            symbol="SELECTED-ACCOUNT",
            direction="sell",
            stake="5",
            status="executed",
        )
        request = APIRequestFactory().get("/api/dashboard/trade_history/?days=30&limit=8")
        SessionMiddleware(lambda current_request: None).process_request(request)
        request.session[SESSION_KEY] = selected.pk
        request.session.save()
        force_authenticate(request, user=self.user)
        response = DashboardViewSet.as_view({"get": "trade_history"})(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["symbol"] for row in response.data["data"]], ["SELECTED-ACCOUNT"])
