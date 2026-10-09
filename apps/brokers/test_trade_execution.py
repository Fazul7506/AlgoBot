from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.brokers.adapters.deriv import DerivAdapter
from apps.brokers.models import Broker, BrokerAccount, BrokerConnection, ExecutionReport, Order, TradeReconciliation
from apps.brokers.exceptions import BrokerConnectionError, BrokerRoutingError
from apps.brokers.views import TradeReconciliationViewSet
from apps.brokers.services import ExecutionEngine
from apps.market_data.models import MarketSnapshot, MarketSymbol


class CanonicalTradeExecutionTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="trade-test", password="test-pass")
        self.broker = Broker.objects.create(name="Deriv", broker_type="deriv", status="active", supports_live=True)
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="VRTC123",
            status="active",
            credentials={"account_type": "demo"},
            balance=Decimal("100"),
            equity=Decimal("100"),
            free_margin=Decimal("100"),
        )
        self.account.set_access_token("test-access-token")
        self.account.save(update_fields=["access_token"])
        BrokerConnection.objects.create(broker=self.broker, broker_account=self.account, status="connected")
        symbol = MarketSymbol.objects.create(symbol="R_100", display_name="Volatility 100", market="Volatility Indices")
        MarketSnapshot.objects.create(symbol=symbol, last_price="1.25", timestamp=timezone.now())

    @override_settings(BROKER_ORDER_TIMEOUT_SECONDS=2)
    def test_manual_trade_uses_canonical_account_and_returns_execution_report(self):
        fake_report = {"status": "filled", "broker_order_id": "C123", "execution_price": "1.25", "fees": 0}
        adapter = SimpleNamespace(place_order=AsyncMock(return_value=fake_report))
        with patch("apps.brokers.services.BrokerRegistry.adapter", return_value=adapter):
            report = ExecutionEngine().submit(self.user, account=self.account, symbol="R_100", direction="buy", order_type="market", stake=Decimal("1"), client_order_id="web-regression-1")
        self.assertIsInstance(report, ExecutionReport)
        self.assertEqual(report.order.account_id, self.account.id)
        self.assertEqual(report.order.broker_order_id, "C123")
        self.assertEqual(report.status, "filled")
        self.assertEqual(Order.objects.filter(client_order_id="web-regression-1").count(), 1)

    def test_execution_accepts_broker_verified_nested_realtime_account_type(self):
        self.account.credentials = {"realtime": {"account_type": "demo"}}
        self.account.save(update_fields=["credentials"])
        fake_report = {"status": "filled", "broker_order_id": "C-NESTED", "execution_price": "1.25", "fees": 0}
        adapter = SimpleNamespace(place_order=AsyncMock(return_value=fake_report))
        with patch("apps.brokers.services.BrokerRegistry.adapter", return_value=adapter):
            report = ExecutionEngine().submit(
                self.user,
                account=self.account,
                symbol="R_100",
                direction="buy",
                order_type="market",
                stake=Decimal("1"),
                client_order_id="nested-realtime-account-type",
            )
        self.assertEqual(report.order.broker_order_id, "C-NESTED")
        self.assertEqual(report.order.routing_context["account_type"], "demo")
        adapter.place_order.assert_awaited_once()

    def test_same_client_order_id_does_not_place_a_second_order(self):
        fake_report = {"status": "filled", "broker_order_id": "C124", "execution_price": "1.25", "fees": 0}
        adapter = SimpleNamespace(place_order=AsyncMock(return_value=fake_report))
        with patch("apps.brokers.services.BrokerRegistry.adapter", return_value=adapter):
            first = ExecutionEngine().submit(self.user, account=self.account, symbol="R_100", direction="buy", order_type="market", stake=Decimal("1"), client_order_id="web-regression-2")
            second = ExecutionEngine().submit(self.user, account=self.account, symbol="R_100", direction="buy", order_type="market", stake=Decimal("1"), client_order_id="web-regression-2")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(adapter.place_order.await_count, 1)
        self.assertEqual(Order.objects.filter(client_order_id="web-regression-2").count(), 1)

    def test_deriv_maps_buy_and_sell_to_distinct_contracts(self):
        adapter = DerivAdapter.__new__(DerivAdapter)
        adapter.account = SimpleNamespace(currency="USD")
        adapter.credentials = {"account_type": "demo"}
        responses = [
            {"contracts_for": {"available": [{"contract_type": "CALL"}, {"contract_type": "PUT"}]}},
            {"proposal": {"id": "P1", "ask_price": "1"}},
            {"buy": {"contract_id": "C1", "buy_price": "1"}},
            {"contracts_for": {"available": [{"contract_type": "CALL"}, {"contract_type": "PUT"}]}},
            {"proposal": {"id": "P2", "ask_price": "1"}},
            {"buy": {"contract_id": "C2", "buy_price": "1"}},
        ]
        adapter._request = AsyncMock(side_effect=responses)
        with patch("apps.brokers.adapters.deriv.settings.ALLOW_LIVE_TRADING", True):
            buy = __import__("asyncio").run(adapter.place_order(SimpleNamespace(order_type="market", direction="buy", contract_type="", stake=1, quantity=1, routing_context={}, symbol="R_100")))
            sell = __import__("asyncio").run(adapter.place_order(SimpleNamespace(order_type="market", direction="sell", contract_type="", stake=1, quantity=1, routing_context={}, symbol="R_100")))
        self.assertEqual(buy["contract_type"], "CALL")
        self.assertEqual(sell["contract_type"], "PUT")


    def test_malformed_success_response_is_unknown_not_falsely_executed(self):
        adapter = SimpleNamespace(place_order=AsyncMock(return_value={}))
        with patch("apps.brokers.services.BrokerRegistry.adapter", return_value=adapter):
            with self.assertRaises(BrokerConnectionError):
                ExecutionEngine().submit(
                    self.user,
                    account=self.account,
                    symbol="R_100",
                    direction="buy",
                    order_type="market",
                    stake=Decimal("1"),
                    client_order_id="malformed-broker-response",
                )
        order = Order.objects.get(client_order_id="malformed-broker-response")
        self.assertEqual(order.status, "pending")
        self.assertTrue(order.routing_context["reconciliation_required"])
        self.assertFalse(order.execution_reports.exists())
        self.assertTrue(TradeReconciliation.objects.filter(trade__algobot_order_id=order.pk).exists())

    def test_reconciliation_records_are_scoped_to_the_owning_users_orders(self):
        own_order = Order.objects.create(
            user=self.user, broker=self.broker, account=self.account, symbol="R_100", direction="buy"
        )
        foreign_user = get_user_model().objects.create_user(username="other-trade-user", password="test-pass")
        foreign_account = BrokerAccount.objects.create(
            user=foreign_user, broker=self.broker, account_id="FOREIGN-123", status="active",
            credentials={"account_type": "demo"},
        )
        foreign_order = Order.objects.create(
            user=foreign_user, broker=self.broker, account=foreign_account, symbol="R_100", direction="sell"
        )
        own_rec = TradeReconciliation.objects.create(
            broker=self.broker, trade={"algobot_order_id": own_order.pk}, matched=False
        )
        TradeReconciliation.objects.create(
            broker=self.broker, trade={"algobot_order_id": foreign_order.pk}, matched=False
        )
        view = TradeReconciliationViewSet()
        view.request = SimpleNamespace(user=self.user)
        visible_ids = set(view.get_queryset().values_list("id", flat=True))
        self.assertEqual(visible_ids, {own_rec.pk})

    @override_settings(ALLOW_LIVE_TRADING=True)
    def test_real_account_cannot_trade_through_broker_without_live_capability(self):
        self.broker.supports_live = False
        self.broker.save(update_fields=["supports_live"])
        self.account.credentials = {"account_type": "real"}
        self.account.save(update_fields=["credentials"])
        with self.assertRaisesRegex(BrokerRoutingError, "not live-trading capable"):
            ExecutionEngine().submit(
                self.user, account=self.account, symbol="R_100", direction="buy",
                order_type="market", stake=Decimal("1"), client_order_id="unsupported-live-broker",
            )
        self.assertFalse(Order.objects.filter(client_order_id="unsupported-live-broker").exists())
