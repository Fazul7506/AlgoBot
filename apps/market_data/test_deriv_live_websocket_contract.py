import asyncio
import json
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.brokers.exceptions import BrokerAuthenticationError

from .signal_views import _authenticated_live_ticks


class DerivLiveWebSocketContractTests(SimpleTestCase):
    def test_live_signal_feed_uses_otp_url_and_never_sends_authorize_to_public_options_socket(self):
        class Adapter:
            timeout = 10

            def __init__(self):
                self.otp_calls = 0

            def _authenticated_ws_url(self):
                self.otp_calls += 1
                return "wss://api.derivws.com/trading/v1/options/ws/demo?otp=test"

        class FakeWebSocket:
            def __init__(self):
                self.sent = []
                self.messages = [
                    json.dumps({
                        "msg_type": "tick",
                        "req_id": 1,
                        "tick": {"symbol": "R_100", "quote": 123.45, "epoch": 1900000000},
                    })
                ]

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def send(self, payload):
                self.sent.append(json.loads(payload))

            async def recv(self):
                return self.messages.pop(0)

        adapter = Adapter()
        socket = FakeWebSocket()

        async def fake_to_thread(func, *args):
            return func(*args)

        with patch("apps.market_data.signal_views.websockets.connect", return_value=socket), patch(
            "apps.market_data.signal_views.asyncio.to_thread", side_effect=fake_to_thread
        ):
            ticks, _latency = asyncio.run(_authenticated_live_ticks(adapter, ["R_100"]))

        self.assertEqual(adapter.otp_calls, 1)
        self.assertEqual(ticks["R_100"]["quote"], 123.45)
        self.assertEqual(socket.sent, [{"ticks": "R_100", "subscribe": 0, "req_id": 1}])
        self.assertNotIn("authorize", socket.sent[0])

    def test_authentication_error_from_otp_session_is_propagated(self):
        class Adapter:
            timeout = 10

            def _authenticated_ws_url(self):
                return "wss://api.derivws.com/trading/v1/options/ws/demo?otp=test"

        class FakeWebSocket:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def send(self, payload):
                return None

            async def recv(self):
                return json.dumps({
                    "msg_type": "error",
                    "error": {"code": "AuthorizationRequired", "message": "session expired"},
                })

        async def fake_to_thread(func, *args):
            return func(*args)

        with patch("apps.market_data.signal_views.websockets.connect", return_value=FakeWebSocket()), patch(
            "apps.market_data.signal_views.asyncio.to_thread", side_effect=fake_to_thread
        ):
            with self.assertRaises(BrokerAuthenticationError):
                asyncio.run(_authenticated_live_ticks(Adapter(), ["R_100"]))
