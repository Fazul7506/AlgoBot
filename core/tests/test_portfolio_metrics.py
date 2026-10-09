from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.brokers.models import Broker, BrokerAccount
from apps.execution.models import BrokerTradeHistory
from core.views_portfolio_v2 import _settled_trade_metrics


class PortfolioMetricsHardeningTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="portfolio-metrics-test", password="test-password")
        self.broker = Broker.objects.create(name="Portfolio Test Broker", broker_type="deriv", status="active")
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="PORTFOLIO-METRICS-1",
            status="active",
            credentials={"account_type": "demo"},
        )

    def test_no_settled_broker_pnl_is_reported_as_unavailable(self):
        BrokerTradeHistory.objects.create(
            user=self.user,
            broker_account=self.account,
            symbol="R_100",
            status="unknown",
        )
        metrics = _settled_trade_metrics(self.user)
        self.assertEqual(metrics["trade_count"], 1)
        self.assertEqual(metrics["closed_count"], 0)
        self.assertIsNone(metrics["net_pnl"])
        self.assertIsNone(metrics["win_rate"])
        self.assertFalse(metrics["has_trade_pnl"])

    def test_settled_pnl_and_win_rate_use_broker_history_only(self):
        now = timezone.now()
        BrokerTradeHistory.objects.create(
            user=self.user,
            broker_account=self.account,
            symbol="R_100",
            status="sold",
            profit_loss=Decimal("8.50"),
            settlement_time=now,
        )
        BrokerTradeHistory.objects.create(
            user=self.user,
            broker_account=self.account,
            symbol="R_75",
            status="expired",
            profit_loss=Decimal("-3.50"),
            settlement_time=now,
        )
        metrics = _settled_trade_metrics(self.user)
        self.assertEqual(metrics["trade_count"], 2)
        self.assertEqual(metrics["closed_count"], 2)
        self.assertEqual(metrics["wins"], 1)
        self.assertEqual(metrics["losses"], 1)
        self.assertEqual(metrics["win_rate"], 50.0)
        self.assertEqual(metrics["net_pnl"], Decimal("5.00000000"))
        self.assertTrue(metrics["has_trade_pnl"])
