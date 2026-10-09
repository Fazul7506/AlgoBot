from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.brokers.models import Broker, BrokerAccount, Position
from core.dashboard_api import DashboardViewSet


class DashboardAccountSnapshotTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="dashboard-snapshot-test", password="test-password")
        self.broker = Broker.objects.create(name="Dashboard Test Broker", broker_type="deriv", status="active")
        self.account = BrokerAccount.objects.create(
            user=self.user, broker=self.broker, account_id="DASHBOARD-SNAPSHOT",
            status="active", credentials={"account_type": "demo"},
        )

    def _overview(self):
        request = APIRequestFactory().get("/api/dashboard/account_overview/")
        force_authenticate(request, user=self.user)
        with patch("core.dashboard_api.get_active_account", return_value=self.account):
            return DashboardViewSet.as_view({"get": "account_overview"})(request)

    def test_unsynced_model_defaults_are_not_reported_as_broker_snapshot(self):
        response = self._overview()
        account = response.data["data"]["account"]
        self.assertIsNone(account["balance"])
        self.assertIsNone(account["equity"])
        self.assertIsNone(account["free_margin"])
        self.assertEqual(account["data_freshness"], "unknown")

    def test_synced_zero_balance_and_margin_are_preserved_as_real_values(self):
        self.account.balance = Decimal("0")
        self.account.equity = Decimal("0")
        self.account.free_margin = Decimal("0")
        self.account.last_synced_at = timezone.now()
        self.account.save(update_fields=["balance", "equity", "free_margin", "last_synced_at"])
        response = self._overview()
        account = response.data["data"]["account"]
        self.assertEqual(account["balance"], Decimal("0"))
        self.assertEqual(account["equity"], Decimal("0"))
        self.assertEqual(account["free_margin"], Decimal("0"))
        self.assertEqual(account["data_freshness"], "fresh")

    def test_future_sync_timestamp_is_not_marked_fresh(self):
        self.account.last_synced_at = timezone.now() + timedelta(seconds=120)
        self.account.save(update_fields=["last_synced_at"])
        response = self._overview()
        self.assertEqual(response.data["data"]["account"]["data_freshness"], "stale")

    def test_performance_summary_uses_canonical_position_profit_field(self):
        Position.objects.create(
            broker=self.broker, account=self.account, symbol="R_100",
            status="closed", profit=Decimal("12.50"),
        )
        Position.objects.create(
            broker=self.broker, account=self.account, symbol="R_75",
            status="closed", profit=Decimal("-3.25"),
        )
        request = APIRequestFactory().get("/api/dashboard/performance_summary/")
        force_authenticate(request, user=self.user)
        with patch("core.dashboard_api.get_active_account", return_value=self.account):
            response = DashboardViewSet.as_view({"get": "performance_summary"})(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["best_trade"], Decimal("12.50"))
        self.assertEqual(response.data["data"]["worst_trade"], Decimal("-3.25"))
