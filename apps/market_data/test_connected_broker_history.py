from django.test import TestCase

from apps.market_data.historical import persist_broker_chart_history, persist_broker_tick_history
from apps.market_data.models import Candle, MarketSymbol, Tick


class ConnectedBrokerHistoryPersistenceTests(TestCase):
    def setUp(self):
        self.symbol = MarketSymbol.objects.create(
            symbol="BROKER_HISTORY_TEST",
            display_name="Connected Broker History Test",
            market="Derived Indices",
            broker="deriv",
            is_active=True,
            is_tradable=True,
        )

    def test_broker_candles_are_validated_and_persisted_with_provenance(self):
        result = persist_broker_chart_history(
            self.symbol.symbol,
            "1m",
            [
                {"epoch": 120, "open": "100", "high": "103", "low": "99", "close": "102", "volume": 2},
                {"epoch": 121, "open": "100", "high": "103", "low": "99", "close": "102", "volume": 2},
                {"epoch": 180, "open": "100", "high": "99", "low": "98", "close": "101", "volume": 2},
            ],
        )

        self.assertEqual(result["source"], "connected_broker")
        self.assertEqual(result["valid"], 1)
        self.assertEqual(result["rejected"], 2)
        candle = Candle.objects.get(symbol=self.symbol, timeframe="1m", epoch=120)
        self.assertEqual(candle.source, "connected_broker")
        self.assertEqual(str(candle.close), "102.00000000")

    def test_broker_ticks_are_deduplicated_and_persisted(self):
        result = persist_broker_tick_history(
            self.symbol.symbol,
            [{"epoch": 100, "quote": "100.5"}, {"epoch": 100, "quote": "100.5"}, {"epoch": 101, "quote": "-1"}],
        )

        self.assertEqual(result["source"], "connected_broker")
        self.assertEqual(result["valid"], 1)
        self.assertEqual(result["rejected"], 1)
        self.assertEqual(Tick.objects.filter(symbol=self.symbol).count(), 1)
