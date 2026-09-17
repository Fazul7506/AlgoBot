"""Broker-agnostic AI training data pipeline.

All research data comes from the persisted canonical market_data.Candle store.
Broker APIs are ingestion sources, never a training/research data source.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone

from apps.market_data.models import MarketSymbol, Tick
from apps.market_data.historical import normalize_timeframe
from apps.market_data.research_data import ResearchDataService


class AIDataPipeline:
    """Read canonical persisted broker data and prepare deterministic datasets."""

    MIN_CANDLES = 250

    def __init__(self):
        self.research_data = ResearchDataService()

    def snapshot(self, timeframe="M1", lookback_hours=168, symbol=None):
        timeframe = normalize_timeframe(timeframe)
        cutoff_epoch = int((timezone.now() - timedelta(hours=lookback_hours)).timestamp())
        if symbol:
            market = self.research_data.market(symbol)
            rows = self.research_data.candles(
                market.symbol, timeframe, limit=10000, start_epoch=cutoff_epoch
            )
            return [
                {"broker": market.broker, "symbol": market.symbol, "timeframe": timeframe, **row}
                for row in rows
            ]

        rows = []
        for market in MarketSymbol.objects.filter(is_active=True, is_tradable=True).iterator():
            candles = self.research_data.candles(
                market.symbol, timeframe, limit=10000, start_epoch=cutoff_epoch
            )
            rows.extend(
                {"broker": market.broker, "symbol": market.symbol, "timeframe": timeframe, **row}
                for row in candles
            )
        return rows

    def health(self, timeframe="M1"):
        timeframe = normalize_timeframe(timeframe)
        cutoff_epoch = int((timezone.now() - timedelta(hours=1)).timestamp())
        result = []
        for item in MarketSymbol.objects.filter(is_active=True, is_tradable=True).iterator():
            candles = self.research_data.candles(
                item.symbol, timeframe, limit=10000, start_epoch=cutoff_epoch
            )
            ticks = Tick.objects.filter(symbol=item, epoch__gte=cutoff_epoch).count()
            latest = self.research_data.latest(item.symbol, timeframe)
            result.append({
                "broker": item.broker,
                "symbol": item.symbol,
                "candles_last_hour": len(candles),
                "ticks_last_hour": ticks,
                "latest_candle_epoch": latest["epoch"] if latest else None,
                "ready": bool(candles),
            })
        return result

    def training_summary(self, timeframe="M1", lookback_hours=168):
        timeframe = normalize_timeframe(timeframe)
        rows = self.snapshot(timeframe=timeframe, lookback_hours=lookback_hours)
        return {
            "timeframe": timeframe,
            "lookback_hours": lookback_hours,
            "rows": len(rows),
            "brokers": sorted({row["broker"] for row in rows}),
            "symbols": sorted({row["symbol"] for row in rows}),
            "ready": len(rows) >= self.MIN_CANDLES,
        }

    def dataset(self, symbol, timeframe="M1", limit=5000):
        """Return chronologically ordered persisted OHLCV rows for model construction."""
        return self.research_data.candles(symbol, timeframe, limit=limit)

    def dataset_metadata(self, symbol, timeframe="M1") -> dict[str, Any]:
        """Return provenance identifying the canonical persisted research source."""
        timeframe = normalize_timeframe(timeframe)
        market_symbol = self.research_data.market(symbol)
        latest = self.research_data.latest(symbol, timeframe)
        return {
            "broker": market_symbol.broker,
            "symbol": market_symbol.symbol,
            "timeframe": timeframe,
            "source": "market_data.Candle",
            "storage": "database",
            "latest_epoch": latest["epoch"] if latest else None,
            "generated_at": timezone.now().isoformat(),
        }
