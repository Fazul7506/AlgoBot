from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.brokers.exceptions import BrokerOrderError
from apps.brokers.models import Broker, BrokerAccount, BrokerConnection
from apps.execution.models import Order
from apps.execution.views import OrderViewSet


@override_settings(BROKER_MARKET_DATA_MAX_AGE_SECONDS=30, ALLOW_LIVE_TRADING=False)
class TerminalLivePreviewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="terminal-live-preview", password="test-password"
        )
        self.broker = Broker.objects.create(
            name="Deriv",
            broker_type="deriv",
            status="active",
            supports_live=True,
            metadata={"auth": "oauth"},
        )
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="VRTC-TERMINAL",
            status="active",
            balance="100.00",
            credentials={"account_type": "demo"},
        )
        self.account.set_access_token("isolated-test-token")
        self.account.save(update_fields=["access_token"])
        BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=self.account,
            status="connected",
        )
        self.factory = APIRequestFactory()

    def preview(self, contract_type="CALL", direction="buy", stake="1.00", duration=60, duration_unit="s"):
        request = self.factory.post(
            "/api/orders/preview/",
            {
                "broker_account": self.account.pk,
                "symbol": "R_100",
                "contract_type": contract_type,
                "direction": direction,
                "order_type": "market",
                "stake": stake,
                "duration": duration,
                "duration_unit": duration_unit,
            },
            format="json",
        )
        force_authenticate(request, user=self.user)
        return OrderViewSet.as_view({"post": "preview"})(request)

    def adapter(self, quote=None, contracts=None):
        return SimpleNamespace(
            get_trade_capabilities=AsyncMock(
                return_value=contracts if contracts is not None else [{"contract_type": "CALL"}]
            ),
            get_market_data=AsyncMock(
                return_value=quote
                if quote is not None
                else {
                    "symbol": "R_100",
                    "price": "100.25",
                    "bid": "100.20",
                    "ask": "100.30",
                    "epoch": int(timezone.now().timestamp()),
                }
            ),
            get_order_preview=AsyncMock(return_value={
                "proposal_id": "isolated-proposal",
                "ask_price": "1.00",
                "payout": "1.90",
                "symbol": "R_100",
                "contract_type": "CALL",
                "currency": "USD",
                "duration": 60,
                "duration_unit": "s",
            }),
        )

    def test_preview_uses_fresh_quote_and_verifies_selected_contract(self):
        adapter = self.adapter()
        with patch("apps.execution.views.BrokerRegistry.adapter", return_value=adapter):
            result = self.preview()

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["status"], "ready")
        self.assertEqual(result.data["source"], "authoritative_pre_trade_preview")
        self.assertEqual(result.data["order"]["contract_type"], "CALL")
        self.assertTrue(result.data["gates"]["contract_verified"])
        self.assertTrue(result.data["gates"]["fresh_market_data"])
        self.assertEqual(result.data["market"]["source"], "selected_broker_live_quote")
        self.assertEqual(result.data["estimate"]["payout"], 1.9)
        self.assertEqual(result.data["estimate"]["potential_profit"], 0.9)
        self.assertTrue(result.data["gates"]["payout_verified"])
        adapter.get_order_preview.assert_awaited_once_with(symbol="R_100", contract_type="CALL", amount=Decimal("1.00"), duration=60, duration_unit="s")
        adapter.get_trade_capabilities.assert_awaited_once_with("R_100")
        adapter.get_market_data.assert_awaited_once_with("R_100")

    def test_preview_rejects_stale_broker_quote(self):
        adapter = self.adapter(
            quote={
                "symbol": "R_100",
                "price": "100.25",
                "epoch": int((timezone.now() - timedelta(minutes=2)).timestamp()),
            }
        )
        with patch("apps.execution.views.BrokerRegistry.adapter", return_value=adapter):
            result = self.preview()

        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "BROKER_MARKET_DATA_STALE")
        self.assertNotEqual(result.data["status"], "ready")

    def test_preview_rejects_contract_missing_from_live_broker_capabilities(self):
        adapter = self.adapter(contracts=[{"contract_type": "PUT"}])
        with patch("apps.execution.views.BrokerRegistry.adapter", return_value=adapter):
            result = self.preview(contract_type="CALL", direction="buy")

        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "BROKER_CONTRACT_UNAVAILABLE")
        adapter.get_market_data.assert_not_awaited()

    def test_preview_rejects_direction_inconsistent_with_contract(self):
        adapter = self.adapter()
        with patch("apps.execution.views.BrokerRegistry.adapter", return_value=adapter):
            result = self.preview(contract_type="CALL", direction="sell")

        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "BROKER_CONTRACT_DIRECTION_MISMATCH")
        adapter.get_market_data.assert_not_awaited()

    def test_preview_rejects_stake_above_risk_profile_limit(self):
        adapter = self.adapter()
        with patch("apps.execution.views.BrokerRegistry.adapter", return_value=adapter):
            result = self.preview(stake="3.00")

        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "PREVIEW_RISK_REJECTED")
        adapter.get_trade_capabilities.assert_not_awaited()

    def test_preview_rejects_zero_stake(self):
        adapter = self.adapter()
        with patch("apps.execution.views.BrokerRegistry.adapter", return_value=adapter):
            result = self.preview(stake="0")

        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "PREVIEW_RISK_REJECTED")
        adapter.get_trade_capabilities.assert_not_awaited()

    def test_terminal_order_history_is_scoped_to_the_selected_account(self):
        other_account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="VRTC-OTHER",
            status="active",
            balance="100.00",
            credentials={"account_type": "demo"},
        )
        first = Order.objects.create(
            user=self.user,
            broker_account=self.account,
            symbol="R_100",
            direction="buy",
            order_type="market",
            contract_type="CALL",
            stake="1.00",
            status="executed",
        )
        Order.objects.create(
            user=self.user,
            broker_account=other_account,
            symbol="R_100",
            direction="buy",
            order_type="market",
            contract_type="CALL",
            stake="1.00",
            status="executed",
        )
        request = self.factory.get("/api/orders/?account_scope=active&limit=8")
        force_authenticate(request, user=self.user)
        with patch("apps.execution.views.get_active_account", return_value=self.account):
            result = OrderViewSet.as_view({"get": "list"})(request)

        self.assertEqual(result.status_code, 200)
        items = result.data.get("results", result.data if isinstance(result.data, list) else [])
        self.assertEqual([row["id"] for row in items], [first.id])


    def test_preview_passes_selected_duration_to_broker_proposal(self):
        adapter = self.adapter()
        adapter.get_order_preview.return_value.update({"duration": 5, "duration_unit": "t"})
        with patch("apps.execution.views.BrokerRegistry.adapter", return_value=adapter):
            result = self.preview(duration=5, duration_unit="t")

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["estimate"]["duration"], 5)
        self.assertEqual(result.data["estimate"]["duration_unit"], "t")
        adapter.get_order_preview.assert_awaited_once_with(
            symbol="R_100",
            contract_type="CALL",
            amount=Decimal("1.00"),
            duration=5,
            duration_unit="t",
        )

    def test_preview_rejects_broker_proposal_failure_without_claiming_ready(self):
        adapter = self.adapter()
        adapter.get_order_preview.side_effect = BrokerOrderError("Required contract parameter is missing")
        with patch("apps.execution.views.BrokerRegistry.adapter", return_value=adapter):
            result = self.preview()

        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "BROKER_PROPOSAL_REJECTED")
        self.assertTrue(result.data["no_order_submitted"])

    def test_preview_rejects_when_plan_order_quota_is_exhausted(self):
        with patch("apps.execution.views.check", return_value=(False, 10, 10)):
            result = self.preview()

        self.assertEqual(result.status_code, 429)
        self.assertEqual(result.data["code"], "ORDER_LIMIT_REACHED")


    def test_preview_rejects_real_account_when_live_trading_is_disabled(self):
        self.account.credentials = {"account_type": "real"}
        self.account.save(update_fields=["credentials"])
        adapter = self.adapter()
        with patch("apps.execution.views.check_live_order", return_value=(True, 0, 5)), patch("apps.execution.views.BrokerRegistry.adapter", return_value=adapter):
            result = self.preview()

        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "LIVE_TRADING_DISABLED")
        adapter.get_trade_capabilities.assert_not_awaited()

