from django.test import TestCase

from .constants import TIMEFRAMES
from .historical import fetch_and_store_all_timeframes, persist_candles
from .models import Candle, MarketSymbol


class HistoricalCandleBackfillIntegrityTests(TestCase):
    def setUp(self):
        self.symbol = MarketSymbol.objects.create(
            symbol="R_100",
            display_name="Volatility 100",
            market="Volatility Indices",
            broker="deriv",
            is_active=True,
            is_tradable=True,
        )

    def test_persist_candles_rejects_bad_ohlc_and_misaligned_epochs(self):
        result = persist_candles(
            "R_100",
            "1m",
            [
                {"epoch": 61, "open": "1", "high": "2", "low": "1", "close": "2"},
                {"epoch": 60, "open": "2", "high": "1", "low": "0", "close": "1"},
            ],
        )
        self.assertEqual(result["valid"], 0)
        self.assertEqual(Candle.objects.count(), 0)

    def test_persist_candles_deduplicates_duplicate_epochs(self):
        result = persist_candles(
            "R_100",
            "1m",
            [
                {"epoch": 60, "open": "1", "high": "3", "low": "1", "close": "2"},
                {"epoch": 60, "open": "1", "high": "4", "low": "1", "close": "3"},
            ],
        )
        self.assertEqual(result["valid"], 1)
        self.assertEqual(Candle.objects.filter(symbol=self.symbol, timeframe="1m", epoch=60).count(), 1)
        self.assertEqual(Candle.objects.get(symbol=self.symbol, timeframe="1m", epoch=60).high, 4)

    def test_backfill_requires_positive_request_pacing(self):
        with self.assertRaisesMessage(ValueError, "request_interval"):
            fetch_and_store_all_timeframes("R_100", count=250, request_interval=0)

    def test_supported_native_timeframes_remain_broker_authoritative(self):
        self.assertIn("1m", TIMEFRAMES)
        self.assertIn("1d", TIMEFRAMES)
