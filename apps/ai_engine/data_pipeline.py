"""Broker-agnostic AI training data pipeline.

Broker adapters normalize data into market_data.Candle/Tick records. The AI
reads only this canonical store, keeping provider payloads out of models.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any

from django.utils import timezone

from apps.market_data.historical import normalize_timeframe
from apps.market_data.models import Candle, MarketSymbol, Tick


class AIDataPipeline:
    """Read canonical broker data and prepare deterministic training snapshots."""

    MIN_CANDLES = 250

    def snapshot(self, timeframe="M1", lookback_hours=168, symbol=None):
        timeframe = normalize_timeframe(timeframe)
        cutoff_epoch = int((timezone.now() - timedelta(hours=lookback_hours)).timestamp())
        qs = Candle.objects.filter(timeframe=timeframe, epoch__gte=cutoff_epoch)
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
        timeframe = normalize_timeframe(timeframe)
        symbols = MarketSymbol.objects.filter(is_active=True, is_tradable=True)
        cutoff_epoch = int((timezone.now() - timedelta(hours=1)).timestamp())
        result = []
        for item in symbols.iterator():
            candles = Candle.objects.filter(symbol=item, timeframe=timeframe, epoch__gte=cutoff_epoch).count()
            ticks = Tick.objects.filter(symbol=item, epoch__gte=cutoff_epoch).count()
            latest_candle = Candle.objects.filter(symbol=item, timeframe=timeframe).order_by("-epoch").first()
            result.append({
                "broker": item.broker,
                "symbol": item.symbol,
                "candles_last_hour": candles,
                "ticks_last_hour": ticks,
                "latest_candle_epoch": latest_candle.epoch if latest_candle else None,
                "ready": candles > 0,
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
        """Return chronologically ordered OHLCV rows for model construction."""
        timeframe = normalize_timeframe(timeframe)
        market_symbol = MarketSymbol.objects.filter(symbol=symbol, is_active=True).first()
        if not market_symbol:
            raise ValueError(f"Unknown active market symbol: {symbol}")
        return list(
            Candle.objects.filter(symbol=market_symbol, timeframe=timeframe)
            .order_by("epoch")
            .values("epoch", "open", "high", "low", "close", "volume")[:limit]
        )

    def dataset_metadata(self, symbol, timeframe="M1") -> dict[str, Any]:
        """Return provenance information to store alongside a trained model."""
        timeframe = normalize_timeframe(timeframe)
        market_symbol = MarketSymbol.objects.filter(symbol=symbol, is_active=True).first()
        if not market_symbol:
            raise ValueError(f"Unknown active market symbol: {symbol}")
        return {
            "broker": market_symbol.broker,
            "symbol": market_symbol.symbol,
            "timeframe": timeframe,
            "source": "market_data.Candle",
            "generated_at": timezone.now().isoformat(),
        }
