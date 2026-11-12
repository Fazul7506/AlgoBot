from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.brokers.adapters.deriv import DerivAdapter
from apps.brokers.exceptions import BrokerConnectionError


class DerivAuthenticatedEndpointTests(SimpleTestCase):
    @override_settings(
        DERIV_OPTIONS_ACCOUNTS_URL="https://api.derivws.com/trading/v1/options/accounts"
    )
    @patch.object(DerivAdapter, "_account_id", return_value="VRTC12345")
    @patch.object(DerivAdapter, "_token", return_value="test-token")
    @patch("apps.brokers.adapters.deriv.requests.post")
    def test_accepts_provider_issued_secure_websocket_endpoint(
        self, post, token, account_id
    ):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "data": {"url": "wss://api.derivws.com/trading/v1/options/ws"}
        }
        post.return_value = response

        adapter = DerivAdapter(broker=Mock(), account=Mock())
        endpoint = adapter._authenticated_ws_url()

        self.assertEqual(
            endpoint, "wss://api.derivws.com/trading/v1/options/ws"
        )
        post.assert_called_once()

    @override_settings(
        DERIV_OPTIONS_ACCOUNTS_URL="https://api.derivws.com/trading/v1/options/accounts"
    )
    @patch.object(DerivAdapter, "_account_id", return_value="VRTC12345")
    @patch.object(DerivAdapter, "_token", return_value="test-token")
    @patch("apps.brokers.adapters.deriv.requests.post")
    def test_rejects_malformed_provider_websocket_endpoint(
        self, post, token, account_id
    ):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"data": {"url": "https://"}}
        post.return_value = response

        adapter = DerivAdapter(broker=Mock(), account=Mock())
        with self.assertRaisesMessage(
            BrokerConnectionError,
            "Deriv returned an invalid authenticated WebSocket endpoint",
        ):
            adapter._authenticated_ws_url()
