from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from apps.brokers.adapters.deriv import DerivAdapter


class DerivHistoricalDataAuthenticationTests(IsolatedAsyncioTestCase):
    async def test_candle_history_uses_the_connected_account_session(self):
        adapter = DerivAdapter.__new__(DerivAdapter)
        adapter._request = AsyncMock(return_value={"candles": [{"epoch": 60}]})

        result = await adapter.get_chart_history(
            "R_100",
            mode="candles",
            count=100,
            granularity=60,
            start=60,
            end=120,
        )

        adapter._request.assert_awaited_once_with(
            {
                "ticks_history": "R_100",
                "end": 120,
                "start": 60,
                "style": "candles",
                "granularity": 60,
            },
            authenticated=True,
        )
        self.assertEqual(result["source"], "connected_broker")
        self.assertEqual(result["items"], [{"epoch": 60}])

    async def test_tick_history_uses_the_connected_account_session(self):
        adapter = DerivAdapter.__new__(DerivAdapter)
        adapter._request = AsyncMock(
            return_value={"history": {"times": [60, 120], "prices": [100.1, 100.2]}}
        )

        result = await adapter.get_chart_history(
            "R_100",
            mode="ticks",
            start=60,
            end=120,
        )

        adapter._request.assert_awaited_once_with(
            {
                "ticks_history": "R_100",
                "end": 120,
                "start": 60,
                "style": "ticks",
            },
            authenticated=True,
        )
        self.assertEqual(result["source"], "connected_broker")
        self.assertEqual(result["items"], [
            {"epoch": 60, "quote": 100.1},
            {"epoch": 120, "quote": 100.2},
        ])
