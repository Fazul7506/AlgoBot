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
TIMEFRAME_GRANULARITY = {"1s": 1, "5s": 5, "15s": 15, "30s": 30, "1m": 60, "2m": 120, "5m": 300, "10m": 600, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}
TIMEFRAME_ALIASES = {"M1": "1m", "M2": "2m", "M5": "5m", "M10": "10m", "M15": "15m", "M30": "30m", "H1": "1h", "H4": "4h", "D1": "1d"}

def normalize_timeframe(timeframe: str) -> str:
    value = str(timeframe or "1m").strip()
    canonical = TIMEFRAME_ALIASES.get(value.upper(), value.lower())
    if canonical not in TIMEFRAME_GRANULARITY:
        raise ValueError(f"Unsupported candle timeframe: {timeframe}")
    return canonical

def _ws_url() -> str:
    url = getattr(settings, "DERIV_PUBLIC_WS_URL", "")
    if not url:
        raise RuntimeError("DERIV_PUBLIC_WS_URL is not configured")
    return url

async def _fetch(symbol: str, count: int, granularity: int) -> list[dict]:
    payload = {"ticks_history": symbol, "end": "latest", "count": min(max(int(count), 1), 5000), "style": "candles", "granularity": granularity}
    async with websockets.connect(_ws_url(), open_timeout=10, close_timeout=10) as ws:
        await ws.send(json.dumps(payload))
        raw = await asyncio.wait_for(ws.recv(), timeout=15)
    response = json.loads(raw)
    if response.get("error"):
        raise RuntimeError(response["error"].get("message", "Deriv rejected historical candle request"))
    return response.get("candles", [])

def fetch_and_store(symbol: str, timeframe: str = "1m", count: int = 5000) -> dict:
    timeframe = normalize_timeframe(timeframe)
    market_symbol = MarketSymbol.objects.filter(symbol=symbol, is_active=True).first()
    if not market_symbol:
        raise ValueError(f"Unknown active market symbol: {symbol}")
    candles = asyncio.run(_fetch(symbol, count, TIMEFRAME_GRANULARITY[timeframe]))
    if not candles:
        return {"symbol": symbol, "timeframe": timeframe, "received": 0, "stored_total": 0}
    rows = []
    for item in candles:
        try:
            rows.append(Candle(symbol=market_symbol, timeframe=timeframe, epoch=int(item["epoch"]), open=Decimal(str(item["open"])), high=Decimal(str(item["high"])), low=Decimal(str(item["low"])), close=Decimal(str(item["close"])), volume=Decimal(str(item.get("volume", 0) or 0))))
        except (KeyError, TypeError, ValueError, ArithmeticError):
            logger.warning("Skipping malformed historical candle", extra={"symbol": symbol, "timeframe": timeframe})
    with transaction.atomic():
        Candle.objects.bulk_create(rows, ignore_conflicts=True, batch_size=500)
    stored = Candle.objects.filter(symbol=market_symbol, timeframe=timeframe).count()
    return {"symbol": symbol, "timeframe": timeframe, "received": len(candles), "valid": len(rows), "stored_total": stored}
