import asyncio
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

    def test_stream_backoff_grows_when_connections_open_then_drop_quickly(self):
        class FakeSocket:
            async def send(self, payload):
                return None

            async def recv(self):
                raise OSError("socket closed")

            async def close(self):
                return None

        class CancelSocket(FakeSocket):
            async def recv(self):
                raise asyncio.CancelledError()

        sockets = [FakeSocket(), FakeSocket(), CancelSocket()]
        connect = AsyncMock(side_effect=sockets)
        callback = AsyncMock()
        adapter = DerivAdapter(broker=Mock(), account=Mock())

        async def exercise():
            with patch("apps.brokers.adapters.deriv.websockets.connect", connect), \\
                patch("apps.brokers.adapters.deriv.time.monotonic", side_effect=[0, 1, 2, 3, 4]), \\
                patch("apps.brokers.adapters.deriv.asyncio.sleep", new=AsyncMock()) as sleep:
                with self.assertRaises(asyncio.CancelledError):
                    await adapter._stream(
                        [{"ticks": "R_100", "subscribe": 1}],
                        callback=callback,
                        authenticated=False,
                        stream_name="test",
                    )
            self.assertEqual([call.args[0] for call in sleep.await_args_list], [1.0, 2.0])
            reconnect_events = [
                call.args[0] for call in callback.await_args_list
                if call.args[0].get("status") == "reconnecting"
            ]
            self.assertEqual([event["retry_in"] for event in reconnect_events], [1.0, 2.0])

        asyncio.run(exercise())

