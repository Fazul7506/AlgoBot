from django.test import TestCase

from .historical import persist_candles
from .models import Candle, MarketSymbol
from .research_data import ResearchDataService


class BrokerDataProvenanceTests(TestCase):
    def setUp(self):
        self.market = MarketSymbol.objects.create(
            symbol="R_100",
            display_name="Volatility 100",
            market="Derived Indices",
            broker="deriv",
            is_active=True,
            is_tradable=True,
        )

    def test_deriv_ohlc_upsert_replaces_tick_derived_candle(self):
        Candle.objects.create(
            symbol=self.market,
            timeframe="1m",
            epoch=1900000020,
            open="100",
            high="101",
            low="99",
            close="100",
            source="tick_stream",
        )
        result = persist_candles(
            "R_100",
            "1m",
            [{
                "epoch": 1900000020,
                "open": 110,
                "high": 112,
                "low": 109,
                "close": 111,
                "volume": 12,
            }],
        )
        candle = Candle.objects.get(symbol=self.market, timeframe="1m", epoch=1900000020)
        self.assertEqual(candle.source, "deriv_candles")
        self.assertEqual(str(candle.close), "111.00000000")
        self.assertEqual(result["source"], "deriv_candles")

    def test_research_never_uses_tick_derived_minute_candle(self):
        Candle.objects.create(
            symbol=self.market,
            timeframe="1m",
            epoch=1900000020,
            open="100",
            high="101",
            low="99",
            close="100",
            source="tick_stream",
        )
        self.assertEqual(
            ResearchDataService().candles("R_100", "1m", limit=10),
            [],
        )
