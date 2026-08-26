from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings

from apps.brokers.adapters.deriv import DerivAdapter
from apps.brokers.models import Broker, BrokerAccount, BrokerConnection, ExecutionReport, Order
from apps.brokers.services import ExecutionEngine


class CanonicalTradeExecutionTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="trade-test", password="test-pass")
        self.broker = Broker.objects.create(name="Deriv", broker_type="deriv", status="active", supports_live=True)
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="VRTC123",
            status="active",
            is_preferred=True,
            credentials={"account_type": "demo"},
            balance=Decimal("100"),
            equity=Decimal("100"),
            free_margin=Decimal("100"),
        )
        # Canonical broker routing requires both usable credentials and an
        # account-scoped connected BrokerConnection. Keep the execution tests
        # focused on routing/idempotency by creating that connection explicitly.
        self.account.set_access_token("test-access-token")
        self.account.save(update_fields=["access_token"])
        BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=self.account,
            status="connected",
        )

    @override_settings(BROKER_ORDER_TIMEOUT_SECONDS=2)
    def test_manual_trade_uses_canonical_account_and_returns_execution_report(self):
        fake_report = {"status": "filled", "broker_order_id": "C123", "execution_price": "1.25", "fees": 0}
        adapter = SimpleNamespace(place_order=AsyncMock(return_value=fake_report))
        with patch("apps.brokers.services.BrokerRegistry.adapter", return_value=adapter):
            report = ExecutionEngine().submit(
                self.user,
                account=self.account,
                symbol="R_100",
                direction="buy",
                order_type="market",
                stake=Decimal("1"),
                client_order_id="web-regression-1",
            )
        self.assertIsInstance(report, ExecutionReport)
        self.assertEqual(report.order.account_id, self.account.id)
        self.assertEqual(report.order.broker_order_id, "C123")
        self.assertEqual(report.status, "filled")
        self.assertEqual(Order.objects.filter(client_order_id="web-regression-1").count(), 1)

    def test_same_client_order_id_does_not_place_a_second_order(self):
        fake_report = {"status": "filled", "broker_order_id": "C124", "execution_price": "1.25", "fees": 0}
        adapter = SimpleNamespace(place_order=AsyncMock(return_value=fake_report))
        with patch("apps.brokers.services.BrokerRegistry.adapter", return_value=adapter):
            first = ExecutionEngine().submit(
                self.user,
                account=self.account,
                symbol="R_100",
                direction="buy",
                order_type="market",
                stake=Decimal("1"),
                client_order_id="web-regression-2",
            )
            second = ExecutionEngine().submit(
                self.user,
                account=self.account,
                symbol="R_100",
                direction="buy",
                order_type="market",
                stake=Decimal("1"),
                client_order_id="web-regression-2",
            )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(adapter.place_order.await_count, 1)
        self.assertEqual(Order.objects.filter(client_order_id="web-regression-2").count(), 1)

    def test_deriv_maps_buy_and_sell_to_distinct_contracts(self):
        adapter = DerivAdapter.__new__(DerivAdapter)
        adapter.account = SimpleNamespace(currency="USD")
        adapter.credentials = {"account_type": "demo"}
        responses = [
            {"proposal": {"id": "P1", "ask_price": "1"}},
            {"buy": {"contract_id": "C1", "buy_price": "1"}},
            {"proposal": {"id": "P2", "ask_price": "1"}},
            {"buy": {"contract_id": "C2", "buy_price": "1"}},
        ]
        adapter._request = AsyncMock(side_effect=responses)
        with patch("apps.brokers.adapters.deriv.settings.ALLOW_LIVE_TRADING", True):
            buy = __import__("asyncio").run(adapter.place_order(SimpleNamespace(order_type="market", direction="buy", contract_type="", stake=1, quantity=1, routing_context={}, symbol="R_100")))
            sell = __import__("asyncio").run(adapter.place_order(SimpleNamespace(order_type="market", direction="sell", contract_type="", stake=1, quantity=1, routing_context={}, symbol="R_100")))
        self.assertEqual(buy["contract_type"], "CALL")
        self.assertEqual(sell["contract_type"], "PUT")
