from django.test import TestCase

from apps.market_data.constants import TIMEFRAMES
from apps.market_data.historical import (
    _aggregate_ticks_to_candles,
    persist_broker_chart_history,
    persist_tick_candles,
)
from apps.market_data.models import Candle, MarketSymbol, Tick
from apps.market_data.repositories import MarketRepository
from apps.market_data.services import TickService


class MarketDataEngineTests(TestCase):
    def setUp(self):
        self.symbol = MarketSymbol.objects.create(
            symbol="R_100",
            display_name="Volatility 100",
            market="Volatility Indices",
        )

    def test_tick_ingest_generates_repository_data_and_every_canonical_timeframe(self):
        tick = TickService().ingest({
            "symbol": "R_100",
            "quote": "100.00",
            "bid": "99.90",
            "ask": "100.10",
            "epoch": 1000,
            "volume": "1",
        })
        self.assertEqual(MarketRepository.latest_tick("R_100")["quote"], "100.00")
        for timeframe in TIMEFRAMES:
            self.assertTrue(
                Candle.objects.filter(symbol=self.symbol, timeframe=timeframe).exists(),
                timeframe,
            )
        self.assertEqual(tick.spread, tick.ask - tick.bid)

    def test_broker_ohlc_history_is_idempotently_persisted(self):
        items = [
            {
                "epoch": 1700000000,
                "open": 100,
                "high": 102,
                "low": 99,
                "close": 101,
                "volume": 12,
            },
            {
                "epoch": 1700000060,
                "open": 101,
                "high": 103,
                "low": 100,
                "close": 102,
                "volume": 15,
            },
        ]
        first = persist_broker_chart_history("R_100", "1m", items)
        second = persist_broker_chart_history("R_100", "1m", items)
        self.assertEqual(first["valid"], 2)
        self.assertEqual(second["stored_total"], 2)
        self.assertEqual(
            Candle.objects.filter(symbol=self.symbol, timeframe="1m").count(),
            2,
        )

    def test_persisted_ticks_can_build_subminute_and_tick_candles(self):
        Tick.objects.bulk_create([
            Tick(symbol=self.symbol, quote="100.00", epoch=1000, volume="1"),
            Tick(symbol=self.symbol, quote="101.00", epoch=1001, volume="2"),
            Tick(symbol=self.symbol, quote="99.00", epoch=1004, volume="3"),
        ])
        ticks = list(Tick.objects.filter(symbol=self.symbol).order_by("epoch"))
        built = _aggregate_ticks_to_candles("R_100", ticks, "5s")
        tick_built = persist_tick_candles(
            "R_100",
            [{"epoch": tick.epoch, "quote": str(tick.quote)} for tick in ticks],
        )
        self.assertEqual(built, 1)
        self.assertEqual(tick_built, 3)
        candle = Candle.objects.get(symbol=self.symbol, timeframe="5s", epoch=1000)
        self.assertEqual(str(candle.open), "100.00000000")
        self.assertEqual(str(candle.high), "101.00000000")
        self.assertEqual(str(candle.low), "99.00000000")
        self.assertEqual(str(candle.close), "99.00000000")
