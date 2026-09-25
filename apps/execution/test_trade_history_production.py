import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from apps.brokers.models import Broker, BrokerAccount
from apps.execution.models import BrokerTradeHistory

from apps.brokers.adapters.deriv import DerivAdapter
from apps.execution.trade_history import normalize_deriv_trade


class DerivTradeHistoryAuthTests(SimpleTestCase):
    @override_settings(DERIV_OPTIONS_ACCOUNTS_URL="https://api.derivws.com/trading/v1/options/accounts")
    @patch("apps.brokers.adapters.deriv.requests.post")
    def test_oauth_otp_request_uses_bearer_auth_without_legacy_app_id_header(self, post):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"data": {"url": "wss://api.derivws.com/trading/v1/options/ws/demo?otp=test"}}
        post.return_value = response

        broker = Mock(broker_type="deriv")
        account = Mock(
            broker=broker,
            account_id="DOT123456",
            token_status="active",
            is_token_expired=False,
        )
        account.get_access_token.return_value = "oauth-access-token"
        adapter = DerivAdapter(broker=broker, account=account, credentials={})

        self.assertEqual(
            adapter._authenticated_ws_url(),
            "wss://api.derivws.com/trading/v1/options/ws/demo?otp=test",
        )
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer oauth-access-token")
        self.assertNotIn("Deriv-App-ID", headers)


class DerivTradeHistoryFactTests(SimpleTestCase):
    def test_stake_never_falls_back_to_signed_statement_amount(self):
        row = normalize_deriv_trade(
            {
                "transaction_id": "TX-1",
                "contract_id": 123,
                "amount": "-5",
                "transaction_time": 1760000000,
            },
            {
                "contract_id": 123,
                "contract_type": "CALL",
                "currency": "USD",
                "profit": "-5",
            },
        )
        self.assertIsNone(row["stake"])
        self.assertEqual(row["profit_loss"], -5)


class DerivTradeHistoryAsyncOrmTests(TransactionTestCase):
    reset_sequences = True

    def test_async_sync_persists_without_touching_django_orm_in_async_context(self):
        user = get_user_model().objects.create_user(
            username="trade-history-async",
            password="test-pass",
        )
        broker = Broker.objects.create(
            name="Deriv Async Test",
            broker_type="deriv",
            status="active",
        )
        account = BrokerAccount.objects.create(
            user=user,
            broker=broker,
            account_id="ASYNC-TRADE-HISTORY",
            status="active",
        )

        adapter = Mock()
        adapter.get_trade_history = AsyncMock(return_value=[
            {
                "contract_id": 987654,
                "transaction_id": "TX-987654",
                "transaction_time": 1760000000,
                "currency": "USD",
            }
        ])
        adapter.get_trade_contract = AsyncMock(return_value={
            "contract_id": 987654,
            "underlying_symbol": "1HZ100V",
            "contract_type": "CALL",
            "buy_price": "1.25",
            "payout": "2.00",
            "profit": "0.75",
            "status": "won",
            "date_start": 1760000000,
        })

        with patch("apps.execution.trade_history.BrokerRegistry.adapter", return_value=adapter):
            from apps.execution.trade_history import DerivTradeHistoryService

            result = asyncio.run(
                DerivTradeHistoryService(account).sync(limit=100)
            )

        self.assertEqual(result["state"], "success")
        self.assertEqual(result["count"], 1)
        row = BrokerTradeHistory.objects.get(
            broker_account=account,
            broker_contract_id="987654",
        )
        self.assertEqual(row.symbol, "1HZ100V")
        self.assertEqual(row.stake, Decimal("1.25"))
        self.assertEqual(row.profit_loss, Decimal("0.75"))
        self.assertIsNotNone(account.__class__.objects.get(pk=account.pk).last_synced_at)


class DerivTradeHistoryAccountsAuthTests(SimpleTestCase):
    @override_settings(DERIV_OPTIONS_ACCOUNTS_URL="https://api.derivws.com/trading/v1/options/accounts")
    @patch("apps.brokers.adapters.deriv.requests.get")
    def test_oauth_account_lookup_does_not_send_legacy_app_id(self, get):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"data": [{"account_id": "DOT123456"}]}
        get.return_value = response

        broker = Mock(broker_type="deriv")
        account = Mock(
            broker=broker,
            account_id="DOT123456",
            token_status="active",
            is_token_expired=False,
        )
        account.get_access_token.return_value = "oauth-access-token"
        adapter = DerivAdapter(broker=broker, account=account, credentials={})

        self.assertEqual(asyncio.run(adapter.get_accounts()), [{"account_id": "DOT123456"}])
        headers = get.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer oauth-access-token")
        self.assertNotIn("Deriv-App-ID", headers)
