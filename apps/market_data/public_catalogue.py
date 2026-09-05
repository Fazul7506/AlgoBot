from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from . import broker_native
from .models import MarketSymbol
from .serializers import MarketSymbolSerializer


def _limit(request, default=100, maximum=500):
    try:
        raw = request.query_params.get("limit", request.query_params.get("page_size", default))
        return max(1, min(int(raw), maximum))
    except (TypeError, ValueError):
        return default


def _catalogue_data(request):
    """Return plain catalogue data; never call a decorated DRF view internally."""
    account = broker_native._account(getattr(request, "user", None), request=request)
    try:
        payload = cache.get(broker_native.CATALOGUE_CACHE)
        if payload is None:
            response = broker_native._public_deriv({"active_symbols": "brief"})
            raw = response.get("active_symbols") or []
            if not isinstance(raw, list):
                raise RuntimeError("Deriv returned an invalid active_symbols payload")
            payload = [
                broker_native._normalise_symbol(item)
                for item in raw
                if isinstance(item, dict) and item.get("underlying_symbol")
            ]
            payload = [item for item in payload if item["is_active"]]
            if payload:
                cache.set(broker_native.CATALOGUE_CACHE, payload, timeout=30)
                try:
                    broker_native._persist_catalogue(payload)
                except Exception:
                    pass
        if payload:
            return {
                "status": "ok",
                "source": "connected_broker_catalogue" if account else "public_broker_catalogue",
                "broker": account.broker.name if account else "Deriv",
                "account_id": account.account_id if account else None,
                "symbols": payload,
                "count": len(payload),
                "stale": False,
            }
        raise RuntimeError("Deriv returned no active broker instruments")
    except Exception:
        cached = broker_native._cached_database_catalogue()
        if cached:
            return {
                "status": "stale",
                "source": "cached_broker_catalogue",
                "broker": account.broker.name if account else "Deriv",
                "account_id": account.account_id if account else None,
                "symbols": cached,
                "count": len(cached),
                "stale": True,
            }
        return {
            "status": "error",
            "code": "BROKER_CATALOGUE_UNAVAILABLE",
            "detail": "The broker market catalogue is temporarily unavailable.",
            "source": "connected_broker" if account else "public_broker_catalogue",
            "symbols": [],
            "count": 0,
            "stale": False,
        }


@api_view(["GET"])
@permission_classes([AllowAny])
def symbols(request):
    """Compatibility endpoint backed by the authoritative public broker catalogue."""
    data = _catalogue_data(request)
    if data.get("status") == "error":
        return Response(data, status=503)
    rows = list(data.get("symbols") or [])
    return Response(rows[:_limit(request)])


@api_view(["GET"])
@permission_classes([AllowAny])
def markets(request):
    """Return market groups from the same broker source as instrument discovery."""
    data = _catalogue_data(request)
    if data.get("status") == "error":
        return Response(data, status=503)
    rows = list(data.get("symbols") or [])
    groups = sorted({
        str(row.get("market_label") or row.get("market") or "").strip()
        for row in rows
        if row.get("market_label") or row.get("market")
    })
    return Response({
        "markets": groups,
        "count": len(groups),
        "source": data.get("source", "public_broker_catalogue"),
        "stale": bool(data.get("stale")),
    })
