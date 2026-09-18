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
SUBMARKET_MAP = {
    "boom_index": "Boom",
    "crash_index": "Crash",
    "jump_index": "Jump",
    "volatility": "Volatility",
    "random_index": "Random Index",
    "step_index": "Step Index",
    "range_index": "Range Break",
    "1_second": "1 Second",
    "non_stable_coin": "Non-Stable Coin",
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


async def _request(payload: dict) -> dict:
    """Request public market data with bounded network timeouts."""
    try:
        async with websockets.connect(DERIV_PUBLIC_WS, open_timeout=5, close_timeout=5, ping_interval=20, ping_timeout=5) as ws:
            await ws.send(json.dumps(payload))
            response = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
    except (asyncio.TimeoutError, OSError, websockets.WebSocketException, json.JSONDecodeError) as exc:
        raise RuntimeError("Deriv public market data is temporarily unavailable") from exc
    if response.get("error"):
        raise RuntimeError(response["error"].get("message", "Deriv market-data request failed"))
    return response


def _market_name(item: dict) -> str:
    """Resolve market classification from Deriv symbol identity and metadata.

    Deriv's active_symbols payload is authoritative, but some synthetic
    submarket fields are not stable enough to classify Boom/Crash symbols on
    their own. The broker-provided symbol/name is the canonical identity; the
    metadata remains the fallback for non-synthetic instruments.
    """
    symbol = str(item.get("underlying_symbol") or item.get("symbol") or "").strip().upper()
    name = str(item.get("underlying_symbol_name") or item.get("display_name") or "").strip().lower()
    identity = f"{symbol} {name}"
    if symbol.startswith("BOOM") or "boom" in name:
        return "Boom"
    if symbol.startswith("CRASH") or "crash" in name:
        return "Crash"
    if symbol.startswith("JD") or "jump" in name:
        return "Jump Indices"
    if symbol.startswith(("R_", "1HZ")) or "volatility" in name:
        return "Volatility Indices"
    if symbol.startswith(("RB", "stpRNG")) or "step index" in name or "range break" in name:
        return "Derived Indices"
    raw = str(item.get("market") or item.get("underlying_symbol_type") or "synthetic_index").lower()
    for key, value in MARKET_MAP.items():
        if key in raw:
            return value
    return "Derived Indices"


def _sub_market_name(item: dict) -> str:
    raw = str(item.get("submarket") or item.get("subgroup") or "").strip()
    if not raw:
        return ""
    return SUBMARKET_MAP.get(raw.lower(), raw.replace("_", " ").title())


def _sync_one_symbol(item: dict) -> bool:
    symbol = str(item.get("underlying_symbol") or item.get("symbol") or "").strip()
    if not symbol or len(symbol) > 40:
        return False
    pip = item.get("pip_size") or item.get("pip")
    defaults = {
        "broker": "deriv",
        "display_name": str(item.get("underlying_symbol_name") or item.get("display_name") or symbol)[:160],
        "market": _market_name(item),
        "sub_market": _sub_market_name(item)[:120],
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
    """Refresh the cached broker catalogue without allowing concurrent bursts."""
    if not cache.add(MARKET_SYNC_LOCK, "1", timeout=15):
        raise RuntimeError("Deriv market catalogue refresh is already in progress")
    try:
        response = asyncio.run(_request({"active_symbols": "brief"}))
        symbols = response.get("active_symbols", [])
        if not isinstance(symbols, list):
            raise RuntimeError("Deriv returned an invalid active_symbols payload")
        active_values = {
            str(item.get("underlying_symbol") or item.get("symbol") or "").strip()
            for item in symbols
            if isinstance(item, dict)
        }
        active_values.discard("")
        synced = sum(_sync_one_symbol(item) for item in symbols if isinstance(item, dict))
        if active_values:
            MarketSymbol.objects.filter(
                broker="deriv",
                is_active=True,
            ).exclude(symbol__in=active_values).update(is_active=False, is_tradable=False)
        return synced
    finally:
        try:
            cache.delete(MARKET_SYNC_LOCK)
        except Exception:
            pass


def fetch_contracts_for(symbol: str) -> dict:
    """Return the current broker-published contract capabilities for one symbol.

    This is deliberately capability metadata only. It never invents a
    contract, duration, stake, barrier, or payout. Those values require a
    concrete proposal request and account context.
    """
    symbol = str(symbol or "").strip()
    if not symbol:
        raise ValueError("A Deriv symbol is required")

    cache_key = f"algobot:deriv:contracts-for:{symbol}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    response = asyncio.run(_request({"contracts_for": symbol}))
    payload = response.get("contracts_for") or {}
    available = payload.get("available") or []
    if not isinstance(available, list):
        raise RuntimeError(f"Deriv returned an invalid contracts_for payload for {symbol}")

    contracts = []
    for item in available:
        if not isinstance(item, dict):
            continue
        contracts.append(
            {
                "underlying_symbol": str(item.get("underlying_symbol") or symbol),
                "contract_type": item.get("contract_type"),
                "contract_category": item.get("contract_category"),
                "market": item.get("market"),
                "submarket": item.get("submarket"),
                "exchange_name": item.get("exchange_name"),
                "expiry_type": item.get("expiry_type"),
                "sentiment": item.get("sentiment"),
                "barriers": item.get("barriers"),
            }
        )

    result = {
        "symbol": symbol,
        "source": "deriv_public_websocket",
        "available": contracts,
        "available_contract_types": sorted(
            {str(item["contract_type"]) for item in contracts if item.get("contract_type")}
        ),
        "available_contract_families": sorted(
            {str(item["contract_category"]) for item in contracts if item.get("contract_category")}
        ),
        "expiry_types": sorted(
            {str(item["expiry_type"]) for item in contracts if item.get("expiry_type")}
        ),
        "sentiments": sorted(
            {str(item["sentiment"]) for item in contracts if item.get("sentiment")}
        ),
        "fetched_at": int(__import__("time").time()),
    }
    cache.set(cache_key, result, 300)
    return result


def fetch_tick(symbol: str) -> dict:
    """Fetch one authoritative broker quote without writing to the database.

    Persistence belongs to TickService.ingest so every caller uses the same
    idempotent ingestion path. This prevents the broker endpoint from writing
    the same tick once during fetch and again during normalization.
    """
    response = asyncio.run(_request({"ticks": symbol}))
    tick = response.get("tick") or {}
    quote = tick.get("quote")
    if quote is None:
        raise RuntimeError(f"Deriv returned no quote for {symbol}")
    if not MarketSymbol.objects.filter(symbol=symbol, is_active=True).exists():
        raise RuntimeError(f"Symbol {symbol} is not present in the broker market catalogue")
    return {
        "symbol": symbol,
        "quote": float(quote),
        "bid": float(tick["bid"]) if tick.get("bid") is not None else None,
        "ask": float(tick["ask"]) if tick.get("ask") is not None else None,
        "epoch": int(tick.get("epoch") or 0),
        "volume": float(tick.get("volume") or 0),
    }
