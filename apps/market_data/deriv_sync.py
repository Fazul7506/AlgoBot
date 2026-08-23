from __future__ import annotations

import asyncio
import json
from decimal import Decimal, InvalidOperation

import websockets
from django.db import IntegrityError, transaction

from .models import MarketSymbol, Tick


DERIV_PUBLIC_WS = "wss://api.derivws.com/trading/v1/options/ws/public"
MARKET_MAP = {
    "forex": "Forex",
    "cryptocurrency": "Crypto",
    "cryptocurrency_market": "Crypto",
    "indices": "Stock Indices",
    "stock_indices": "Stock Indices",
    "synthetic_index": "Derived Indices",
    "synthetics": "Derived Indices",
    "volatility": "Volatility Indices",
    "boom": "Boom",
    "crash": "Crash",
    "jump": "Jump Indices",
    "commodities": "Commodities",
}


def _safe_decimal(value, default="0") -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else default))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


async def _request(payload: dict) -> dict:
    """Request public market data from Deriv's public market WebSocket."""
    try:
        async with websockets.connect(DERIV_PUBLIC_WS, open_timeout=10, close_timeout=10) as ws:
            await ws.send(json.dumps(payload))
            response = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
    except (asyncio.TimeoutError, OSError, websockets.WebSocketException, json.JSONDecodeError) as exc:
        raise RuntimeError("Deriv public market data is temporarily unavailable") from exc
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
    """Persist one Deriv symbol without allowing one bad/racing row to abort the batch."""
    symbol = str(item.get("underlying_symbol") or item.get("symbol") or "").strip()
    if not symbol or len(symbol) > 40:
        return False

    defaults = {
        "broker": "deriv",
        "display_name": str(item.get("underlying_symbol_name") or item.get("display_name") or symbol)[:160],
        "market": _market_name(item),
        "sub_market": str(item.get("submarket") or item.get("subgroup") or "")[:120],
        "pip_size": max(0, min(int(_safe_decimal(item.get("pip_size") or item.get("pip") or 2)), 65535)),
        "is_active": True,
        "is_tradable": bool(item.get("exchange_is_open", True)) and not bool(item.get("is_trading_suspended", False)),
    }

    try:
        with transaction.atomic():
            MarketSymbol.objects.update_or_create(symbol=symbol, defaults=defaults)
        return True
    except IntegrityError:
        # A concurrent sync can race on the unique symbol constraint. Re-read and
        # update the existing row instead of turning the entire endpoint into 500.
        try:
            MarketSymbol.objects.filter(symbol=symbol).update(**defaults)
            return True
        except Exception:
            return False
    except (TypeError, ValueError):
        return False


def sync_active_symbols() -> int:
    response = asyncio.run(_request({"active_symbols": "brief"}))
    symbols = response.get("active_symbols", [])
    if not isinstance(symbols, list):
        raise RuntimeError("Deriv returned an invalid active_symbols payload")
    return sum(_sync_one_symbol(item) for item in symbols if isinstance(item, dict))


def fetch_tick(symbol: str) -> dict:
    response = asyncio.run(_request({"ticks": symbol}))
    tick = response.get("tick") or {}
    quote = tick.get("quote")
    if quote is None:
        raise RuntimeError(f"Deriv returned no quote for {symbol}")

    market_symbol, _ = MarketSymbol.objects.get_or_create(
        symbol=symbol,
        defaults={"broker": "deriv", "display_name": symbol, "market": "Derived Indices"},
    )
    bid, ask = tick.get("bid"), tick.get("ask")
    spread = _safe_decimal(ask) - _safe_decimal(bid) if bid is not None and ask is not None else Decimal("0")
    epoch = int(tick.get("epoch") or 0)
    obj, _ = Tick.objects.get_or_create(
        symbol=market_symbol,
        epoch=epoch,
        quote=quote,
        defaults={"bid": bid, "ask": ask, "spread": spread, "volume": tick.get("volume") or 0},
    )
    return {
        "symbol": symbol,
        "quote": float(obj.quote),
        "bid": float(obj.bid) if obj.bid is not None else None,
        "ask": float(obj.ask) if obj.ask is not None else None,
        "epoch": obj.epoch,
    }
