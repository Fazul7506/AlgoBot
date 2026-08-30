import unittest
from unittest.mock import AsyncMock, Mock

from apps.brokers.adapters.deriv import DerivAdapter


class DerivStreamingAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_prices_creates_real_subscriptions(self):
        adapter = DerivAdapter()
        adapter._start_stream = Mock(return_value={"status": "streaming"})
        result = await adapter.stream_prices(["1HZ100V", "1HZ100V", "frxEURUSD"])

        self.assertEqual(result["status"], "streaming")
        subscriptions = adapter._start_stream.call_args.args[0]
        self.assertEqual([item["ticks"] for item in subscriptions], ["1HZ100V", "frxEURUSD"])
        self.assertTrue(all(item["subscribe"] == 1 for item in subscriptions))
        self.assertFalse(adapter._start_stream.call_args.kwargs["authenticated"])

    async def test_stream_positions_is_authenticated(self):
        adapter = DerivAdapter()
        adapter._start_stream = Mock(return_value={"status": "streaming"})

        await adapter.stream_positions()

        subscriptions = adapter._start_stream.call_args.args[0]
        self.assertEqual(subscriptions[0]["portfolio"], 1)
        self.assertEqual(subscriptions[1]["transaction"], 1)
        self.assertEqual(subscriptions[1]["subscribe"], 1)
        self.assertTrue(adapter._start_stream.call_args.kwargs["authenticated"])

    async def test_dispatch_stream_supports_async_callbacks(self):
        adapter = DerivAdapter()
        callback = AsyncMock()
        await adapter._dispatch_stream(callback, {"msg_type": "tick", "quote": 123.45})
        callback.assert_awaited_once_with({"msg_type": "tick", "quote": 123.45})

    async def test_stream_prices_rejects_empty_symbol_list(self):
        adapter = DerivAdapter()
        with self.assertRaises(Exception):
            await adapter.stream_prices([])
