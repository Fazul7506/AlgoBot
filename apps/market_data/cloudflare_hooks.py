from __future__ import annotations

import hmac
import json
import os

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.market_data.deriv_sync import sync_active_symbols
from apps.market_data.exceptions import ValidationError as MarketDataValidationError
from apps.market_data.services import MarketDataService


def _authorized(request) -> bool:
    expected = os.environ.get("CLOUDFLARE_MARKET_STREAM_TOKEN", "")
    supplied = request.headers.get("Authorization", "")
    return bool(expected) and hmac.compare_digest(supplied, f"Bearer {expected}")


@require_GET
def cloudflare_market_symbols(request):
    if not _authorized(request):
        return JsonResponse({"status": "unauthorized"}, status=401)
    try:
        sync_active_symbols()
    except Exception:
        # Keep streaming from the last known catalogue if the broker catalogue
        # endpoint is temporarily unavailable; fail only when it is empty.
        pass
    symbols = list(
        MarketDataService.symbols.catalogue(
            broker="deriv", active=True, tradable=True
        ).values_list("symbol", flat=True)
    )
    if not symbols:
        return JsonResponse({"status": "no_active_symbols"}, status=503)
    return JsonResponse({"symbols": symbols})


@csrf_exempt
@require_POST
def cloudflare_market_tick(request):
    if not _authorized(request):
        return JsonResponse({"status": "unauthorized"}, status=401)
    try:
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError, UnicodeDecodeError):
        return JsonResponse({"status": "invalid_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"status": "invalid_payload"}, status=400)
    tick = payload.get("tick")
    if not isinstance(tick, dict):
        return JsonResponse({"status": "invalid_tick"}, status=400)

    symbol = str(tick.get("symbol") or "").strip()
    if not symbol or len(symbol) > 64:
        return JsonResponse({"status": "invalid_symbol"}, status=400)
    if not MarketDataService.symbols.catalogue(
        broker="deriv", active=True, tradable=None, symbol=symbol
    ).exists():
        return JsonResponse({"status": "unknown_symbol"}, status=422)

    try:
        stored = MarketDataService().tick_service.ingest({
            "symbol": symbol,
            "quote": tick.get("quote"),
            "bid": tick.get("bid"),
            "ask": tick.get("ask"),
            "epoch": tick.get("epoch"),
            "volume": tick.get("volume", 0),
        })
    except (MarketDataValidationError, TypeError, ValueError) as exc:
        return JsonResponse({"status": "invalid_tick", "detail": str(exc)[:200]}, status=422)
    except Exception:
        # Queue consumers should retry transient database/service failures.
        return JsonResponse({"status": "ingestion_unavailable"}, status=503)

    data = MarketDataService().tick_service.serialize(stored)
    layer = get_channel_layer()
    if layer:
        async_to_sync(layer.group_send)(
            f"algobot-market-{symbol}",
            {"type": "broker.event", "event_type": "market.tick", "payload": data},
        )
    return JsonResponse({"status": "ingested", "tick": data}, status=202)
