from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.strategies.services import LiveMarketContextService


class FakeAdapter:
    async def get_chart_history(self, symbol, mode='candles', count=200, granularity=60):
        return {'items': [
            {'open': 100 + i, 'high': 101 + i, 'low': 99 + i, 'close': 100.5 + i, 'volume': 10, 'epoch': 1700000000 + i * 60}
            for i in range(25)
        ]}


class LiveMarketContextTests(SimpleTestCase):
    def test_timeframe_granularity(self):
        service = LiveMarketContextService()
        self.assertEqual(service._granularity('M1'), 60)
        self.assertEqual(service._granularity('M5'), 300)
        self.assertEqual(service._granularity('H1'), 3600)

    def test_build_returns_non_empty_strategy_and_ai_context(self):
        account = SimpleNamespace(status='active', broker=SimpleNamespace())
        config = SimpleNamespace(broker_account=account, symbol='R_100', timeframe='M1')
        with patch('apps.brokers.services.BrokerRegistry.adapter', return_value=FakeAdapter()):
            market, indicators, handoff = LiveMarketContextService().build(config)
        self.assertEqual(market['source'], 'live_broker')
        self.assertIsNotNone(market['close'])
        self.assertIn('sma5', indicators)
        self.assertIn('sma20', indicators)
        self.assertIn('rsi', indicators)
        self.assertIn('trend', indicators)
        self.assertEqual(handoff['candles_used'], 25)

    def test_build_rejects_missing_active_broker(self):
        config = SimpleNamespace(broker_account=None, symbol='R_100', timeframe='M1')
        with self.assertRaises(RuntimeError):
            LiveMarketContextService().build(config)
