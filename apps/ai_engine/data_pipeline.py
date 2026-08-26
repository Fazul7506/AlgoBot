"""AI market-data ingestion and training-dataset preparation.

Broker adapters normalize data into market_data.Candle/Tick records. This
service reads that canonical store so the AI remains broker-agnostic.
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.market_data.models import Candle, MarketSymbol, Tick


class AIDataPipeline:
    """Read canonical broker data and prepare deterministic training snapshots."""

    def snapshot(self, timeframe="M1", lookback_hours=168, symbol=None):
        cutoff = timezone.now() - timedelta(hours=lookback_hours)
        qs = Candle.objects.filter(timeframe=timeframe, created_at__gte=cutoff)
        if symbol:
            qs = qs.filter(symbol__symbol=symbol)
        qs = qs.select_related("symbol").order_by("symbol__symbol", "epoch")
        rows = []
        for candle in qs.iterator(chunk_size=2000):
            rows.append({
                "broker": candle.symbol.broker,
                "symbol": candle.symbol.symbol,
                "timeframe": candle.timeframe,
                "epoch": candle.epoch,
                "open": float(candle.open),
                "high": float(candle.high),
                "low": float(candle.low),
                "close": float(candle.close),
                "volume": float(candle.volume),
            })
        return rows

    def health(self, timeframe="M1"):
        symbols = MarketSymbol.objects.filter(is_active=True, is_tradable=True)
        cutoff = timezone.now() - timedelta(hours=1)
        result = []
        for item in symbols.iterator():
            candles = Candle.objects.filter(symbol=item, timeframe=timeframe, created_at__gte=cutoff).count()
            ticks = Tick.objects.filter(symbol=item, created_at__gte=cutoff).count()
            result.append({
                "broker": item.broker,
                "symbol": item.symbol,
                "candles_last_hour": candles,
                "ticks_last_hour": ticks,
                "ready": candles > 0,
            })
        return result

    def training_summary(self, timeframe="M1", lookback_hours=168):
        rows = self.snapshot(timeframe=timeframe, lookback_hours=lookback_hours)
        return {
            "timeframe": timeframe,
            "lookback_hours": lookback_hours,
            "rows": len(rows),
            "brokers": sorted({row["broker"] for row in rows}),
            "symbols": sorted({row["symbol"] for row in rows}),
            "ready": bool(rows),
        }
