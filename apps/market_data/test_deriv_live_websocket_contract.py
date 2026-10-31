import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

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
                        "tick": {"symbol": "R_100", "quote": 123.45, "epoch": int(time.time()) - 1},
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
        self.assertEqual(socket.sent, [{"ticks": "R_100", "subscribe": 1, "req_id": 1}])
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

    def test_market_stream_reconnects_and_resubscribes_without_synthesizing_quotes(self):
        from apps.market_data.management.commands.run_market_stream import Command

        class FakeWebSocket:
            def __init__(self, messages):
                self.messages = list(messages)
                self.sent = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def send(self, payload):
                self.sent.append(json.loads(payload))

            async def recv(self):
                message = self.messages.pop(0)
                if isinstance(message, BaseException):
                    raise message
                return json.dumps(message)

        epoch = int(time.time())
        tick_message = {
            "msg_type": "tick",
            "tick": {"symbol": "R_100", "quote": 123.45, "bid": 123.44, "ask": 123.46, "epoch": epoch},
        }
        first = FakeWebSocket([tick_message, RuntimeError("socket closed")])
        second = FakeWebSocket([asyncio.CancelledError()])
        sockets = [first, second]

        def fake_sync_to_async(fn):
            async def call(*args, **kwargs):
                return fn(*args, **kwargs)
            return call

        layer = type("Layer", (), {"group_send": AsyncMock()})()
        with patch("apps.market_data.management.commands.run_market_stream.sync_active_symbols"), \
            patch("apps.market_data.management.commands.run_market_stream.MarketDataService.symbols.catalogue") as markets, \
            patch("apps.market_data.management.commands.run_market_stream.sync_to_async", side_effect=fake_sync_to_async), \
            patch("apps.market_data.management.commands.run_market_stream.websockets.connect", side_effect=lambda *args, **kwargs: sockets.pop(0)) as connect, \
            patch("apps.market_data.management.commands.run_market_stream.get_channel_layer", return_value=layer), \
            patch("apps.market_data.management.commands.run_market_stream.Command.ingest", return_value={"symbol": "R_100", "quote": 123.45, "epoch": epoch}), \
            patch("apps.market_data.management.commands.run_market_stream.asyncio.sleep", new=AsyncMock(return_value=None)):
            markets.return_value.values_list.return_value = ["R_100"]
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(Command().run())

        subscription = {"ticks": "R_100", "subscribe": 1, "req_id": 1}
        self.assertEqual(first.sent, [subscription])
        self.assertEqual(second.sent, [subscription])
        self.assertEqual(connect.call_count, 2)
        layer.group_send.assert_awaited_once()
