"""Broker historical OHLC/tick ingestion for durable research data."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from decimal import Decimal

import websockets
from django.conf import settings
from django.db import transaction

from .constants import TIMEFRAMES
from .models import Candle, MarketSymbol, Tick

logger = logging.getLogger(__name__)

# Deriv's native OHLC endpoint is used for minute-and-higher bars.  Sub-minute
# research bars are built from persisted ticks because the broker does not
# expose every sub-minute granularity in its candle catalogue.
TIMEFRAME_GRANULARITY = {
    timeframe: seconds
    for timeframe, seconds in TIMEFRAMES.items()
    if timeframe != "tick" and seconds >= 60
}
TIMEFRAME_ALIASES = {
    "M1": "1m", "M2": "2m", "M5": "5m", "M10": "10m", "M15": "15m",
    "M30": "30m", "H1": "1h", "H4": "4h", "D1": "1d",
}


def normalize_timeframe(timeframe: str) -> str:
    value = str(timeframe or "1m").strip()
    canonical = TIMEFRAME_ALIASES.get(value.upper(), value.lower())
    if canonical not in TIMEFRAMES:
        raise ValueError(f"Unsupported candle timeframe: {timeframe}")
    return canonical


def _ws_url() -> str:
    url = getattr(settings, "DERIV_PUBLIC_WS_URL", "")
    if not url:
        raise RuntimeError("DERIV_PUBLIC_WS_URL is not configured")
    return url


def _validate_history_count(count: int) -> int:
    value = int(count)
    if value < 1 or value > 5000:
        raise ValueError("Historical Deriv requests must request between 1 and 5000 items per page")
    return value


async def _request(payload: dict) -> dict:
    """Execute one bounded Deriv history request with safe transient retries."""
    last_error = None
    for attempt in range(3):
        try:
            async with websockets.connect(
                _ws_url(), open_timeout=10, close_timeout=10,
                ping_interval=20, ping_timeout=5
            ) as ws:
                await ws.send(json.dumps(payload))
                raw = await asyncio.wait_for(ws.recv(), timeout=15)
            response = json.loads(raw)
            error = response.get("error")
            if error:
                code = str(error.get("code") or "").lower()
                message = str(error.get("message") or "Deriv rejected historical market-data request")
                if not any(marker in code or marker in message.lower()
                           for marker in ("rate", "limit", "timeout", "temporarily", "busy", "server")):
                    raise RuntimeError(message)
                last_error = RuntimeError(message)
            else:
                return response
        except (asyncio.TimeoutError, OSError, websockets.WebSocketException, json.JSONDecodeError) as exc:
            last_error = RuntimeError("Deriv historical market-data request failed temporarily")
            last_error.__cause__ = exc
        if attempt < 2:
            await asyncio.sleep(1.5 * (2 ** attempt))
    raise last_error or RuntimeError("Deriv historical market-data request failed")


async def _fetch_candles(symbol: str, count: int, granularity: int) -> list[dict]:
    payload = {
        "ticks_history": symbol,
        "end": "latest",
        "count": _validate_history_count(count),
        "style": "candles",
        "granularity": granularity,
    }
    return (await _request(payload)).get("candles", [])


async def _fetch_ticks(symbol: str, count: int) -> list[dict]:
    payload = {
        "ticks_history": symbol,
        "end": "latest",
        "count": _validate_history_count(count),
        "style": "ticks",
    }
    history = (await _request(payload)).get("history", {})
    return [
        {"epoch": epoch, "quote": quote}
        for epoch, quote in zip(history.get("times", []), history.get("prices", []))
    ]


def _market_symbol(symbol: str) -> MarketSymbol:
    market_symbol = MarketSymbol.objects.filter(symbol=symbol, is_active=True).first()
    if not market_symbol:
        raise ValueError(f"Unknown active market symbol: {symbol}")
    return market_symbol


def persist_candles(symbol: str, timeframe: str, items: list[dict]) -> dict:
    """Idempotently persist broker OHLC bars without replacing valid history."""
    timeframe = normalize_timeframe(timeframe)
    market_symbol = _market_symbol(symbol)
    unique_items: dict[int, Candle] = {}
    seconds = TIMEFRAMES[timeframe]
    for item in items:
        try:
            epoch = int(item["epoch"])
            open_price = Decimal(str(item["open"]))
            high_price = Decimal(str(item["high"]))
            low_price = Decimal(str(item["low"]))
            close_price = Decimal(str(item["close"]))
            volume = Decimal(str(item.get("volume", 0) or 0))
            if seconds and epoch % seconds != 0:
                raise ValueError("candle epoch is not aligned to its timeframe boundary")
            if high_price < max(open_price, close_price) or low_price > min(open_price, close_price):
                raise ValueError("invalid OHLC relationship")
            unique_items[epoch] = Candle(
                symbol=market_symbol, timeframe=timeframe, epoch=epoch,
                open=open_price, high=high_price, low=low_price, close=close_price,
                volume=volume, source="deriv_candles",
            )
        except (KeyError, TypeError, ValueError, ArithmeticError):
            logger.warning(
                "Skipping malformed historical candle",
                extra={"symbol": symbol, "timeframe": timeframe},
            )
    rows = list(unique_items.values())

    if rows:
        epochs = [row.epoch for row in rows]
        with transaction.atomic():
            existing = {
                row.epoch: row
                for row in Candle.objects.select_for_update().filter(
                    symbol=market_symbol, timeframe=timeframe, epoch__in=epochs
                )
            }
            creates = []
            updates = []
            for row in rows:
                current = existing.get(row.epoch)
                if current is None:
                    row.source = "deriv_candles"
                    creates.append(row)
                    continue
                current.open = row.open
                current.high = row.high
                current.low = row.low
                current.close = row.close
                current.volume = row.volume
                current.source = "deriv_candles"
                updates.append(current)
            if creates:
                Candle.objects.bulk_create(creates, batch_size=500)
            if updates:
                Candle.objects.bulk_update(
                    updates,
                    ["open", "high", "low", "close", "volume", "source"],
                    batch_size=500,
                )

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "received": len(items),
        "valid": len(rows),
        "stored_total": Candle.objects.filter(symbol=market_symbol, timeframe=timeframe).count(),
        "source": "deriv_candles",
    }


def _aggregate_ticks_to_candles(symbol: str, ticks: list[Tick], timeframe: str) -> int:
    """Create missing sub-minute/tick research candles from persisted ticks."""
    timeframe = normalize_timeframe(timeframe)
    seconds = TIMEFRAMES[timeframe]
    market_symbol = _market_symbol(symbol)
    buckets: dict[int, dict[str, Decimal]] = {}

    for tick in sorted(ticks, key=lambda value: value.epoch):
        epoch = tick.epoch if seconds == 0 else tick.epoch - (tick.epoch % seconds)
        quote = tick.quote
        row = buckets.get(epoch)
        if row is None:
            buckets[epoch] = {
                "open": quote,
                "high": quote,
                "low": quote,
                "close": quote,
                "volume": tick.volume,
            }
        else:
            row["high"] = max(row["high"], quote)
            row["low"] = min(row["low"], quote)
            row["close"] = quote
            row["volume"] += tick.volume

    rows = [
        Candle(
            symbol=market_symbol,
            timeframe=timeframe,
            epoch=epoch,
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
        )
        for epoch, row in buckets.items()
    ]
    if rows:
        with transaction.atomic():
            Candle.objects.bulk_create(rows, ignore_conflicts=True, batch_size=500)
    return len(rows)


def persist_broker_chart_history(symbol: str, timeframe: str, items: list[dict]) -> dict:
    """Persist a broker chart response so research pages share one DB source."""
    return persist_candles(symbol, timeframe, items)


def fetch_and_store(symbol: str, timeframe: str = "1m", count: int = 5000) -> dict:
    timeframe = normalize_timeframe(timeframe)
    if timeframe == "tick":
        return fetch_and_store_ticks(symbol, count=count)
    if timeframe not in TIMEFRAME_GRANULARITY:
        raise ValueError(
            f"{timeframe} is a tick-derived timeframe; persisted ticks are required to build it"
        )
    candles = asyncio.run(_fetch_candles(symbol, count, TIMEFRAME_GRANULARITY[timeframe]))
    return persist_candles(symbol, timeframe, candles)


def fetch_and_store_ticks(symbol: str, count: int = 5000) -> dict:
    """Fetch raw broker ticks and persist them; ticks drive all live sub-minute bars."""
    market_symbol = _market_symbol(symbol)
    items = asyncio.run(_fetch_ticks(symbol, count))
    rows: list[Tick] = []
    for item in items:
        try:
            rows.append(
                Tick(
                    symbol=market_symbol,
                    quote=Decimal(str(item["quote"])),
                    epoch=int(item["epoch"]),
                    volume=Decimal("0"),
                )
            )
        except (KeyError, TypeError, ValueError, ArithmeticError):
            logger.warning("Skipping malformed historical tick", extra={"symbol": symbol})

    if rows:
        with transaction.atomic():
            Tick.objects.bulk_create(rows, ignore_conflicts=True, batch_size=500)

    # Rebuild every canonical timeframe that can be derived from these ticks.
    persisted_ticks = list(
        Tick.objects.filter(symbol=market_symbol).order_by("epoch").filter(
            epoch__gte=min((row.epoch for row in rows), default=0)
        )
    ) if rows else []
    built = {}
    for timeframe in TIMEFRAMES:
        if timeframe != "tick" and TIMEFRAMES[timeframe] < 60:
            built[timeframe] = _aggregate_ticks_to_candles(symbol, persisted_ticks, timeframe)
    built["tick"] = persist_tick_candles(symbol, items)
    return {
        "symbol": symbol,
        "received": len(items),
        "valid": len(rows),
        "stored_ticks": Tick.objects.filter(symbol=market_symbol).count(),
        "built_candles": built,
    }


def persist_tick_candles(symbol: str, items: list[dict]) -> int:
    market_symbol = _market_symbol(symbol)
    rows: list[Candle] = []
    for item in items:
        try:
            quote = Decimal(str(item["quote"]))
            rows.append(
                Candle(
                    symbol=market_symbol,
                    timeframe="tick",
                    epoch=int(item["epoch"]),
                    open=quote,
                    high=quote,
                    low=quote,
                    close=quote,
                    volume=Decimal("0"),
                )
            )
        except (KeyError, TypeError, ValueError, ArithmeticError):
            continue
    if rows:
        with transaction.atomic():
            Candle.objects.bulk_create(rows, ignore_conflicts=True, batch_size=500)
    return len(rows)


def fetch_and_store_all_timeframes(
    symbol: str,
    count: int = 5000,
    request_interval: float = 0.30,
    progress_callback=None,
) -> dict:
    """Populate canonical broker history while pacing Deriv WebSocket calls.

    The Deriv API groups market-data calls under a shared 220/minute budget.
    A per-symbol pacing interval prevents a single warm-up job from producing
    an unbounded request burst. The caller can tune the interval for scheduled
    maintenance, but it must remain positive in production.
    """
    _market_symbol(symbol)
    interval = float(request_interval)
    if interval <= 0:
        raise ValueError("request_interval must be greater than zero for production broker backfill")
    results = {}
    first_request = True

    def pace():
        nonlocal first_request
        if not first_request and interval:
            time.sleep(interval)
        first_request = False

    # Native broker bars provide authoritative OHLC for minute-and-higher data.
    for timeframe in TIMEFRAME_GRANULARITY:
        try:
            pace()
            results[timeframe] = fetch_and_store(symbol, timeframe, count)
        except Exception as exc:
            results[timeframe] = {"status": "failed", "error": str(exc)}
        finally:
            if progress_callback:
                progress_callback(timeframe, results[timeframe])

    # Raw broker ticks are the source for tick, 1s, 5s, 15s and 30s research bars.
    try:
        pace()
        results["tick-derived"] = fetch_and_store_ticks(symbol, count=count)
    except Exception as exc:
        results["tick-derived"] = {"status": "failed", "error": str(exc)}
    return {"symbol": symbol, "timeframes": results}
