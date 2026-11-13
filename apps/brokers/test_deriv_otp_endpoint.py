import asyncio
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.brokers.adapters.deriv import DerivAdapter, _stable_reconnect_delay
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

    @patch("apps.brokers.adapters.deriv.websockets.connect", side_effect=ValueError("invalid URI"))
    def test_request_converts_websocket_uri_value_error_to_connection_error(
        self, connect
    ):
        adapter = DerivAdapter(broker=Mock(), account=Mock())
        with self.assertRaisesMessage(
            BrokerConnectionError,
            "Deriv returned an invalid WebSocket endpoint",
        ):
            asyncio.run(adapter._request({"balance": 1}))
        connect.assert_called_once()

    def test_stream_backoff_resets_only_after_stable_connection(self):
        self.assertEqual(_stable_reconnect_delay(8.0, 10.0), 8.0)
        self.assertEqual(_stable_reconnect_delay(8.0, 59.9), 8.0)
        self.assertEqual(_stable_reconnect_delay(8.0, 60.0), 1.0)
