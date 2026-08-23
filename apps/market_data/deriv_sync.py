from __future__ import annotations

import asyncio
import json
import os

import websockets
from django.conf import settings
from django.db import transaction

from .models import MarketSymbol, Tick


MARKET_MAP = {"forex": "Forex", "cryptocurrency": "Crypto", "cryptocurrency_market": "Crypto", "indices": "Stock Indices", "synthetic_index": "Derived Indices", "synthetics": "Derived Indices", "commodities": "Commodities"}


async def _request(payload: dict) -> dict:
    app_id = getattr(settings, "DERIV_APP_ID", "") or os.getenv("DERIV_APP_ID", "")
    uri = getattr(settings, "DERIV_WS_URL", "wss://ws.derivws.com/websockets/v3")
    if app_id:
        uri = f"{uri}?app_id={app_id}"
    async with websockets.connect(uri, open_timeout=10, close_timeout=10) as ws:
        await ws.send(json.dumps(payload))
        response = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        if response.get("error"):
            raise RuntimeError(response["error"].get("message", "Deriv request failed"))
        return response


def _market_name(item: dict) -> str:
    raw = str(item.get("market") or item.get("underlying_symbol_type") or "synthetic_index").lower()
    for key, value in MARKET_MAP.items():
        if key in raw:
            return value
    return "Derived Indices"


def sync_active_symbols() -> int:
    response = asyncio.run(_request({"active_symbols": "brief"}))
    symbols = response.get("active_symbols", [])
    with transaction.atomic():
        for item in symbols:
            symbol = item.get("underlying_symbol") or item.get("symbol")
            if not symbol:
                continue
            MarketSymbol.objects.update_or_create(
                symbol=symbol,
                defaults={
                    "broker": "deriv",
                    "display_name": item.get("underlying_symbol_name") or item.get("display_name") or symbol,
                    "market": _market_name(item),
                    "sub_market": item.get("submarket") or item.get("subgroup") or "",
                    "pip_size": int(item.get("pip_size") or item.get("pip") or 2),
                    "is_active": True,
                    "is_tradable": bool(item.get("exchange_is_open", True)) and not bool(item.get("is_trading_suspended", False)),
                },
            )
    return len(symbols)


def fetch_tick(symbol: str) -> dict:
    response = asyncio.run(_request({"ticks": symbol}))
    tick = response.get("tick") or {}
    quote = tick.get("quote")
    if quote is None:
        raise RuntimeError(f"Deriv returned no quote for {symbol}")
    market_symbol, _ = MarketSymbol.objects.get_or_create(symbol=symbol, defaults={"broker": "deriv", "display_name": symbol, "market": "Derived Indices"})
    bid, ask = tick.get("bid"), tick.get("ask")
    spread = (float(ask) - float(bid)) if bid is not None and ask is not None else 0
    obj, _ = Tick.objects.get_or_create(symbol=market_symbol, epoch=int(tick.get("epoch") or 0), quote=quote, defaults={"bid": bid, "ask": ask, "spread": spread, "volume": tick.get("volume") or 0})
    return {"symbol": symbol, "quote": float(obj.quote), "bid": float(obj.bid) if obj.bid is not None else None, "ask": float(obj.ask) if obj.ask is not None else None, "epoch": obj.epoch}
