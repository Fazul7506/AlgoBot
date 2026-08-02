from django.test import TestCase
from apps.market_data.models import MarketSymbol, Candle
from apps.market_data.services import TickService
from apps.market_data.repositories import MarketRepository

class MarketDataEngineTests(TestCase):
    def setUp(self):
        self.symbol = MarketSymbol.objects.create(symbol="R_100", display_name="Volatility 100", market="Volatility Indices")
    def test_tick_ingest_generates_repository_data_and_candles(self):
        tick = TickService().ingest({"symbol": "R_100", "quote": "100.00", "bid": "99.90", "ask": "100.10", "epoch": 1000, "volume": "1"})
        self.assertEqual(MarketRepository.latest_tick("R_100")["quote"], "100.00")
        self.assertTrue(Candle.objects.filter(symbol=self.symbol, timeframe="1m").exists())
        self.assertEqual(tick.spread, tick.ask - tick.bid)
