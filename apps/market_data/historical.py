"""Validated persistence for history returned by the user's connected broker.

Historical data is requested on demand through the active broker adapter in the
API layer. This module contains no autonomous ingestion scheduler or private staging lifecycle.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .constants import TIMEFRAMES
from .models import Candle, MarketSymbol, Tick

logger = logging.getLogger(__name__)

TIMEFRAME_ALIASES = {
    "M1": "1m", "M2": "2m", "M5": "5m", "M10": "10m", "M15": "15m",
    "M30": "30m", "H1": "1h", "H2": "2h", "H4": "4h", "H8": "8h", "D1": "1d",
}


def normalize_timeframe(timeframe: str) -> str:
    value = str(timeframe or "1m").strip()
    canonical = TIMEFRAME_ALIASES.get(value.upper(), value.lower())
    if canonical not in TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe '{timeframe}'. Choose a timeframe supported by the connected broker.")
    return canonical


def _market_symbol(symbol: str) -> MarketSymbol:
    market_symbol = MarketSymbol.objects.filter(
        symbol=str(symbol or "").strip(),
        is_active=True,
        is_tradable=True,
    ).first()
    if market_symbol is None:
        raise ValueError(f"Instrument '{symbol}' is not active or tradable in the broker catalogue.")
    return market_symbol


def persist_candles(symbol: str, timeframe: str, items: list[dict]) -> dict:
    """Validate and upsert candle records returned by a connected broker."""
    timeframe = normalize_timeframe(timeframe)
    market_symbol = _market_symbol(symbol)
    seconds = TIMEFRAMES[timeframe]
    incoming = {}
    invalid = 0
    for item in items or []:
        try:
            epoch = int(item["epoch"])
            opening = Decimal(str(item["open"]))
            high = Decimal(str(item["high"]))
            low = Decimal(str(item["low"]))
            close = Decimal(str(item["close"]))
            volume = Decimal(str(item.get("volume", 0) or 0))
            if not all(value.is_finite() for value in (opening, high, low, close, volume)):
                raise ValueError("non-finite OHLC value")
            if seconds and epoch % seconds:
                raise ValueError("candle timestamp does not align with timeframe")
            if high < max(opening, close) or low > min(opening, close) or high < low or volume < 0:
                raise ValueError("invalid OHLC or volume relationship")
            incoming[epoch] = Candle(
                symbol=market_symbol, timeframe=timeframe, epoch=epoch,
                open=opening, high=high, low=low, close=close,
                volume=volume, source="connected_broker",
            )
        except (KeyError, TypeError, ValueError, ArithmeticError, InvalidOperation):
            invalid += 1
            logger.warning(
                "BROKER_HISTORY_CANDLE_REJECTED symbol=%s timeframe=%s reason=invalid_ohlc_or_epoch",
                str(symbol)[:40], timeframe,
            )
    rows = list(incoming.values())
    if rows:
        with transaction.atomic():
            Candle.objects.bulk_create(rows, ignore_conflicts=True, batch_size=500)
            stored = list(Candle.objects.select_for_update().filter(
                symbol=market_symbol, timeframe=timeframe, epoch__in=list(incoming),
            ))
            for row in stored:
                fresh = incoming[row.epoch]
                row.open, row.high, row.low, row.close = fresh.open, fresh.high, fresh.low, fresh.close
                row.volume, row.source = fresh.volume, "connected_broker"
            if stored:
                Candle.objects.bulk_update(
                    stored, ["open", "high", "low", "close", "volume", "source"], batch_size=500,
                )
    return {
        "status": "ok",
        "symbol": market_symbol.symbol,
        "timeframe": timeframe,
        "source": "connected_broker",
        "received": len(items or []),
        "valid": len(rows),
        "rejected": invalid,
        "stored_total": Candle.objects.filter(symbol=market_symbol, timeframe=timeframe).count(),
        "min_epoch": min(incoming, default=None),
        "max_epoch": max(incoming, default=None),
    }


def persist_broker_chart_history(symbol: str, timeframe: str, items: list[dict]) -> dict:
    """Persist candles returned by the authenticated connected-broker adapter."""
    return persist_candles(symbol, timeframe, items)


def persist_broker_tick_history(symbol: str, items: list[dict]) -> dict:
    """Persist tick history returned by the authenticated connected-broker adapter."""
    market_symbol = _market_symbol(symbol)
    rows_by_key = {}
    rejected = 0
    for item in items or []:
        try:
            epoch = int(item["epoch"])
            quote = Decimal(str(item["quote"]))
            if not quote.is_finite() or quote <= 0:
                raise ValueError("invalid quote")
            rows_by_key[(epoch, quote)] = Tick(
                symbol=market_symbol, epoch=epoch, quote=quote, volume=Decimal("0"),
            )
        except (KeyError, TypeError, ValueError, ArithmeticError, InvalidOperation):
            rejected += 1
    rows = list(rows_by_key.values())
    if rows:
        Tick.objects.bulk_create(rows, ignore_conflicts=True, batch_size=500)
        # The canonical research API reads Candle rows for every timeframe,
        # including tick-mode backtests. Keep one tick candle per epoch, matching
        # the model's unique (symbol, timeframe, epoch) boundary.
        candle_by_epoch = {}
        for row in rows:
            candle = candle_by_epoch.get(row.epoch)
            if candle is None:
                candle_by_epoch[row.epoch] = Candle(
                    symbol=market_symbol, timeframe="tick", epoch=row.epoch,
                    open=row.quote, high=row.quote, low=row.quote, close=row.quote,
                    volume=Decimal("0"), source="connected_broker",
                )
            else:
                candle.high = max(candle.high, row.quote)
                candle.low = min(candle.low, row.quote)
                candle.close = row.quote
        Candle.objects.bulk_create(list(candle_by_epoch.values()), ignore_conflicts=True, batch_size=500)
        stored_candles = list(Candle.objects.select_for_update().filter(
            symbol=market_symbol, timeframe="tick", epoch__in=list(candle_by_epoch),
        ))
        for current in stored_candles:
            incoming = candle_by_epoch[current.epoch]
            current.open = incoming.open
            current.high = incoming.high
            current.low = incoming.low
            current.close = incoming.close
            current.source = "connected_broker"
        if stored_candles:
            Candle.objects.bulk_update(stored_candles, ["open", "high", "low", "close", "source"], batch_size=500)
    return {
        "status": "ok", "symbol": market_symbol.symbol, "timeframe": "tick",
        "source": "connected_broker", "received": len(items or []),
        "valid": len(rows), "rejected": rejected,
        "stored_total": Tick.objects.filter(symbol=market_symbol).count(),
    }
