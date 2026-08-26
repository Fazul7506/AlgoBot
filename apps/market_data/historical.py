"""Broker historical OHLC ingestion for training and chart backfill."""
from __future__ import annotations

import asyncio
import json
import logging
from decimal import Decimal

import websockets
from django.conf import settings
from django.db import transaction

from .models import Candle, MarketSymbol

logger = logging.getLogger(__name__)

TIMEFRAME_GRANULARITY = {
    "M1": 60,
    "M2": 120,
    "M5": 300,
    "M10": 600,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H2": 7200,
    "H4": 14400,
    "H8": 28800,
    "D1": 86400,
}


def _ws_url() -> str:
    url = getattr(settings, "DERIV_PUBLIC_WS_URL", "")
    if not url:
        raise RuntimeError("DERIV_PUBLIC_WS_URL is not configured")
    return url


async def _fetch(symbol: str, count: int, granularity: int) -> list[dict]:
    payload = {
        "ticks_history": symbol,
        "end": "latest",
        "count": min(max(int(count), 1), 5000),
        "style": "candles",
        "granularity": granularity,
    }
    async with websockets.connect(_ws_url(), open_timeout=10, close_timeout=10) as ws:
        await ws.send(json.dumps(payload))
        raw = await asyncio.wait_for(ws.recv(), timeout=15)
    response = json.loads(raw)
    if response.get("error"):
        raise RuntimeError(response["error"].get("message", "Deriv rejected historical candle request"))
    return response.get("candles", [])


def fetch_and_store(symbol: str, timeframe: str = "M1", count: int = 5000) -> dict:
    timeframe = timeframe.upper()
    granularity = TIMEFRAME_GRANULARITY.get(timeframe)
    if granularity is None:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    market_symbol = MarketSymbol.objects.filter(symbol=symbol, is_active=True).first()
    if not market_symbol:
        raise ValueError(f"Unknown active market symbol: {symbol}")

    candles = asyncio.run(_fetch(symbol, count, granularity))
    if not candles:
        return {"symbol": symbol, "timeframe": timeframe, "received": 0, "stored": 0}

    rows = []
    for item in candles:
        try:
            rows.append(Candle(
                symbol=market_symbol,
                timeframe=timeframe,
                epoch=int(item["epoch"]),
                open=Decimal(str(item["open"])),
                high=Decimal(str(item["high"])),
                low=Decimal(str(item["low"])),
                close=Decimal(str(item["close"])),
                volume=Decimal(str(item.get("volume", 0) or 0)),
            ))
        except (KeyError, TypeError, ValueError, ArithmeticError):
            logger.warning("Skipping malformed historical candle", extra={"symbol": symbol, "timeframe": timeframe})

    with transaction.atomic():
        Candle.objects.bulk_create(rows, ignore_conflicts=True, batch_size=500)

    stored = Candle.objects.filter(symbol=market_symbol, timeframe=timeframe).count()
    return {"symbol": symbol, "timeframe": timeframe, "received": len(candles), "valid": len(rows), "stored_total": stored}
