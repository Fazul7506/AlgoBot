from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.brokers.models import Broker, BrokerAccount, Order as BrokerOrder, Position
from apps.execution.models import BrokerTradeHistory, Order as LegacyExecutionOrder
from apps.analysis.broker_intelligence import build_account_risk_context


class BrokerRiskContextHardeningTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="risk-context-owner", password="test-password")
        self.broker = Broker.objects.create(name="Risk Context Broker", broker_type="deriv", status="active")
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="RISK-CONTEXT-1",
            status="active",
            balance=Decimal("1000"),
            equity=Decimal("1000"),
            margin=Decimal("100"),
            free_margin=Decimal("500"),
            last_synced_at=timezone.now(),
            credentials={"account_type": "demo"},
        )

    def test_risk_context_uses_broker_orders_and_settled_history_not_legacy_execution_orders(self):
        broker_order = BrokerOrder.objects.create(
            user=self.user, broker=self.broker, account=self.account,
            symbol="R_100", direction="buy", order_type="market",
            stake=Decimal("50"), status="executed", broker_order_id="OPEN-1",
        )
        Position.objects.create(
            broker=self.broker, account=self.account, broker_order_id=broker_order.broker_order_id,
            contract_id="CONTRACT-OPEN-1", symbol="R_100", stake=Decimal("50"), status="open",
        )
        LegacyExecutionOrder.objects.create(
            user=self.user, broker_account=self.account, symbol="R_75", direction="buy",
            order_type="market", stake=Decimal("900"), status="executed",
        )
        BrokerTradeHistory.objects.create(
            user=self.user, broker_account=self.account, broker_order_id="SETTLED-1",
            symbol="R_50", status="sold", profit_loss=Decimal("-5"),
            settlement_time=timezone.now(),
        )

        context = build_account_risk_context(
            self.user,
            self.account,
            confidence=80,
            broker_data={"balance": "1000", "equity": "1000", "margin": "100", "free_margin": "500"},
        )
        self.assertEqual(context["open_stake_exposure"], Decimal("50.00000000"))
        self.assertEqual(context["realized_loss_today"], Decimal("5.00000000"))
        self.assertEqual(context["recommended_stake"], Decimal("20.00000000"))
        self.assertTrue(context["risk_inputs_complete"])

    def test_zero_free_margin_is_not_replaced_with_balance(self):
        context = build_account_risk_context(
            self.user,
            self.account,
            confidence=80,
            broker_data={"balance": "1000", "equity": "1000", "margin": "100", "free_margin": "0"},
        )
        self.assertEqual(context["available_funds"], Decimal("0E-8"))
        self.assertEqual(context["recommended_stake"], Decimal("0E-8"))

    def test_missing_broker_balance_fails_closed_for_stake_recommendation(self):
        context = build_account_risk_context(
            self.user,
            self.account,
            confidence=80,
            broker_data={"free_margin": "500", "margin": "100"},
        )
        self.assertIsNone(context["balance"])
        self.assertEqual(context["recommended_stake"], Decimal("0E-8"))
        self.assertIn("broker_balance_unavailable", context["risk_data_issues"])
