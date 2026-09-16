from __future__ import annotations

import asyncio
import json
import math
from decimal import Decimal, InvalidOperation

import websockets
from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction

from .models import MarketSymbol


DERIV_PUBLIC_WS = getattr(settings, "DERIV_PUBLIC_WS_URL", "wss://api.derivws.com/trading/v1/options/ws/public")
MARKET_SYNC_LOCK = "algobot:deriv:market-sync"
MARKET_MAP = {
    "forex": "Forex", "cryptocurrency": "Crypto", "cryptocurrency_market": "Crypto",
    "indices": "Stock Indices", "stock_indices": "Stock Indices", "synthetic_index": "Derived Indices",
    "synthetics": "Derived Indices", "volatility": "Volatility Indices", "boom": "Boom",
    "crash": "Crash", "jump": "Jump Indices", "commodities": "Commodities",
}


def _safe_decimal(value, default="0") -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else default))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def _decimal_places(value) -> int:
    number = _safe_decimal(value, "0")
    if number <= 0:
        return 0
    try:
        return max(0, min(12, int(round(-math.log10(float(number))))))
    except (ValueError, OverflowError):
        return 0


def _payload_data(response: dict) -> dict:
    """Unwrap the response envelope used by the public Deriv API variants."""
    data = response.get("data")
    return data if isinstance(data, dict) else response


async def _request(payload: dict) -> dict:
    """Request public market data with bounded network timeouts."""
    try:
        async with websockets.connect(
            DERIV_PUBLIC_WS,
            open_timeout=8,
            close_timeout=5,
            ping_interval=20,
            ping_timeout=8,
            max_size=4 * 1024 * 1024,
        ) as ws:
            await ws.send(json.dumps(payload))
            response = json.loads(await asyncio.wait_for(ws.recv(), timeout=8))
    except (asyncio.TimeoutError, OSError, websockets.WebSocketException, json.JSONDecodeError) as exc:
        raise RuntimeError("Deriv public market data is temporarily unavailable") from exc
    if not isinstance(response, dict):
        raise RuntimeError("Deriv returned an invalid market-data response")
    if response.get("error"):
        raise RuntimeError(response["error"].get("message", "Deriv market-data request failed"))
    return response


def _market_name(item: dict) -> str:
    raw = str(item.get("market") or item.get("underlying_symbol_type") or "synthetic_index").lower()
    for key, value in MARKET_MAP.items():
        if key in raw:
            return value
    return "Derived Indices"


def _sync_one_symbol(item: dict) -> bool:
    symbol = str(item.get("underlying_symbol") or item.get("symbol") or "").strip()
    if not symbol or len(symbol) > 40:
        return False
    pip = item.get("pip_size") or item.get("pip")
    defaults = {
        "broker": "deriv",
        "display_name": str(
            item.get("underlying_symbol_name")
            or item.get("display_name")
            or item.get("name")
            or symbol
        )[:160],
        "market": _market_name(item),
        "sub_market": str(item.get("submarket") or item.get("subgroup") or "")[:120],
        "pip_size": _decimal_places(pip),
        "tick_size": _safe_decimal(pip),
        "is_active": True,
        "is_tradable": bool(item.get("exchange_is_open", True)) and not bool(item.get("is_trading_suspended", False)),
    }
    try:
        with transaction.atomic():
            MarketSymbol.objects.update_or_create(symbol=symbol, defaults=defaults)
        return True
    except IntegrityError:
        try:
            MarketSymbol.objects.filter(symbol=symbol).update(**defaults)
            return True
        except Exception:
            return False
    except (TypeError, ValueError):
        return False


def sync_active_symbols() -> int:
    """Refresh the broker catalogue without allowing concurrent bursts."""
    if not cache.add(MARKET_SYNC_LOCK, "1", timeout=30):
        raise RuntimeError("Deriv market catalogue refresh is already in progress")
    try:
        response = _payload_data(asyncio.run(_request({"active_symbols": "brief"})))
        symbols = response.get("active_symbols", [])
        if not isinstance(symbols, list):
            raise RuntimeError("Deriv returned an invalid active_symbols payload")
        return sum(_sync_one_symbol(item) for item in symbols if isinstance(item, dict))
    finally:
        try:
            cache.delete(MARKET_SYNC_LOCK)
        except Exception:
            pass


def fetch_tick(symbol: str) -> dict:
    """Fetch one authoritative broker quote without writing to the database."""
    normalized = str(symbol or "").strip()
    if not normalized or len(normalized) > 40:
        raise RuntimeError("A valid broker symbol is required")
    response = _payload_data(asyncio.run(_request({"ticks": normalized})))
    tick = response.get("tick") or {}
    quote = tick.get("quote")
    if quote is None:
        raise RuntimeError(f"Deriv returned no quote for {normalized}")
    if not MarketSymbol.objects.filter(symbol=normalized, is_active=True).exists():
        raise RuntimeError(f"Symbol {normalized} is not present in the broker market catalogue")
    return {
        "symbol": normalized,
        "quote": float(quote),
        "bid": float(tick["bid"]) if tick.get("bid") is not None else None,
        "ask": float(tick["ask"]) if tick.get("ask") is not None else None,
        "epoch": int(tick.get("epoch") or 0),
        "volume": float(tick.get("volume") or 0),
    }
