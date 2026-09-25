from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

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
