from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from . import broker_native


def _limit(request, default=100, maximum=500):
    try:
        raw = request.query_params.get("limit", request.query_params.get("page_size", default))
        return max(1, min(int(raw), maximum))
    except (TypeError, ValueError):
        return default


def _catalogue_payload(request):
    response = broker_native.catalogue(request)
    data = getattr(response, "data", {}) or {}
    return response, data


@api_view(["GET"])
@permission_classes([AllowAny])
def symbols(request):
    """Compatibility endpoint backed by the authoritative public broker catalogue."""
    response, data = _catalogue_payload(request)
    if getattr(response, "status_code", 500) >= 400:
        return response
    rows = list(data.get("symbols") or [])
    return Response(rows[:_limit(request)])


@api_view(["GET"])
@permission_classes([AllowAny])
def markets(request):
    """Return market groups from the same broker source as instrument discovery."""
    response, data = _catalogue_payload(request)
    if getattr(response, "status_code", 500) >= 400:
        return response
    rows = list(data.get("symbols") or [])
    groups = sorted({str(row.get("market_label") or row.get("market") or "").strip() for row in rows if row.get("market_label") or row.get("market")})
    return Response({"markets": groups, "count": len(groups), "source": data.get("source", "public_broker_catalogue"), "stale": bool(data.get("stale"))})
