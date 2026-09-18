import asyncio
import json
from unittest.mock import patch

from django.test import SimpleTestCase

from .signal_views import _live_deriv_ticks


class DerivLiveWebSocketContractTests(SimpleTestCase):
    def test_live_signal_feed_uses_public_options_socket_and_never_sends_authorize(self):
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

        socket = FakeWebSocket()

        with patch("apps.market_data.signal_views.settings.DERIV_PUBLIC_WS_URL", "wss://api.derivws.com/trading/v1/options/ws/public"), patch(
            "apps.market_data.signal_views.websockets.connect", return_value=socket
        ):
            ticks, _latency = asyncio.run(_live_deriv_ticks(["R_100"]))

        self.assertEqual(ticks["R_100"]["quote"], 123.45)
        self.assertEqual(socket.sent, [{"ticks": "R_100", "subscribe": 0, "req_id": 1}])
        self.assertNotIn("authorize", socket.sent[0])

    def test_public_socket_errors_do_not_become_account_authentication_errors(self):
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

        with patch("apps.market_data.signal_views.settings.DERIV_PUBLIC_WS_URL", "wss://api.derivws.com/trading/v1/options/ws/public"), patch(
            "apps.market_data.signal_views.websockets.connect", return_value=FakeWebSocket()
        ):
            ticks, _latency = asyncio.run(_live_deriv_ticks(["R_100"]))

        self.assertEqual(ticks, {})
