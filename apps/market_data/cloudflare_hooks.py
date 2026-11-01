from __future__ import annotations

import hashlib
import hmac
import json
import os

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

MAX_MARKET_TICK_BODY_BYTES = 16_384
MARKET_TICK_IDEMPOTENCY_TTL_SECONDS = 86_400

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
    if len(request.body) > MAX_MARKET_TICK_BODY_BYTES:
        return JsonResponse({"status": "payload_too_large"}, status=413)
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

    normalized_tick = {
        "symbol": symbol,
        "quote": tick.get("quote"),
        "bid": tick.get("bid"),
        "ask": tick.get("ask"),
        "epoch": tick.get("epoch"),
        "volume": tick.get("volume", 0),
    }
    try:
        fingerprint = hashlib.sha256(
            json.dumps(normalized_tick, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
    except (TypeError, ValueError):
        return JsonResponse({"status": "invalid_tick"}, status=422)
    idempotency_key = f"cf-market-tick:{fingerprint}"

    try:
        claimed = cache.add(
            idempotency_key,
            {"status": "processing"},
            timeout=MARKET_TICK_IDEMPOTENCY_TTL_SECONDS,
        )
        if not claimed:
            existing = cache.get(idempotency_key)
            if not isinstance(existing, dict):
                return JsonResponse({"status": "idempotency_unavailable"}, status=503)
            if existing.get("status") == "processing":
                return JsonResponse({"status": "tick_processing"}, status=503)
            cached_tick = existing.get("tick")
            if existing.get("status") != "ingested" or not isinstance(cached_tick, dict):
                return JsonResponse({"status": "idempotency_unavailable"}, status=503)
            data = cached_tick
        else:
            try:
                stored = MarketDataService().tick_service.ingest(normalized_tick)
                data = MarketDataService().tick_service.serialize(stored)
                cache.set(
                    idempotency_key,
                    {"status": "ingested", "tick": data},
                    timeout=MARKET_TICK_IDEMPOTENCY_TTL_SECONDS,
                )
            except (MarketDataValidationError, TypeError, ValueError) as exc:
                cache.delete(idempotency_key)
                return JsonResponse({"status": "invalid_tick", "detail": str(exc)[:200]}, status=422)
            except Exception:
                cache.delete(idempotency_key)
                return JsonResponse({"status": "ingestion_unavailable"}, status=503)
    except Exception:
        # Fail closed when shared idempotency state is unavailable; the Queue can retry.
        return JsonResponse({"status": "idempotency_unavailable"}, status=503)

    layer = get_channel_layer()
    if layer is None:
        # Never acknowledge a Queue message when live subscribers cannot receive
        # the tick. A retry can fan out the already-ingested tick once Redis/Channels
        # recovers without inserting a duplicate market-data row.
        return JsonResponse({"status": "channel_layer_unavailable"}, status=503)
    try:
        async_to_sync(layer.group_send)(
            f"algobot-market-{symbol}",
            {"type": "broker.event", "event_type": "market.tick", "payload": data},
        )
    except Exception:
        # The stored idempotent result lets a Queue retry re-attempt fan-out.
        return JsonResponse({"status": "fanout_unavailable"}, status=503)
    return JsonResponse(
        {"status": "duplicate" if not claimed else "ingested", "tick": data},
        status=202,
    )
