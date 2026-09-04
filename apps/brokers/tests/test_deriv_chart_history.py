from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from apps.brokers.adapters.deriv import DerivAdapter


class DerivChartHistoryRequestTests(IsolatedAsyncioTestCase):
    async def test_tick_history_does_not_send_invalid_subscribe_zero(self):
        adapter = DerivAdapter()
        adapter._request = AsyncMock(return_value={"history": {"times": [100], "prices": [123.45]}})

        result = await adapter.get_chart_history("frxEURUSD", mode="ticks", count=100)

        payload = adapter._request.await_args.args[0]
        self.assertNotIn("subscribe", payload)
        self.assertEqual(payload["ticks_history"], "frxEURUSD")
        self.assertEqual(result["items"], [{"epoch": 100, "quote": 123.45}])

    async def test_candle_history_uses_broker_granularity(self):
        adapter = DerivAdapter()
        adapter._request = AsyncMock(return_value={"candles": [{"epoch": 100, "open": 1, "high": 2, "low": 0.5, "close": 1.5}]})

        result = await adapter.get_chart_history("frxEURUSD", mode="candles", count=100, granularity=300)

        payload = adapter._request.await_args.args[0]
        self.assertEqual(payload["ticks_history"], "frxEURUSD")
        self.assertEqual(payload["style"], "candles")
        self.assertEqual(payload["granularity"], 300)
        self.assertEqual(result["granularity"], 300)
