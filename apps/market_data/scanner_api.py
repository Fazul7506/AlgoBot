from decimal import Decimal, InvalidOperation
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import MarketSymbol


def _decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def scanner(request):
    """Screen persisted broker snapshots; never invents or substitutes quotes."""
    queryset = MarketSymbol.objects.filter(is_active=True, is_tradable=True).select_related("snapshot")
    market = str(request.query_params.get("market") or "").strip()
    search = str(request.query_params.get("search") or "").strip()
    direction = str(request.query_params.get("direction") or "all").lower().strip()
    sort = str(request.query_params.get("sort") or "change_percent").lower().strip()
    min_change = _decimal(request.query_params.get("min_change"))
    max_change = _decimal(request.query_params.get("max_change"))
    max_spread = _decimal(request.query_params.get("max_spread"))
    if direction not in {"all", "gainers", "losers"}:
        return Response({"status": "error", "code": "INVALID_DIRECTION", "detail": "direction must be all, gainers, or losers."}, status=status.HTTP_400_BAD_REQUEST)
    if sort not in {"change_percent", "price", "spread", "volume", "symbol"}:
        return Response({"status": "error", "code": "INVALID_SORT", "detail": "sort must be change_percent, price, spread, volume, or symbol."}, status=status.HTTP_400_BAD_REQUEST)
    if market:
        queryset = queryset.filter(market=market)
    if search:
        queryset = queryset.filter(Q(symbol__icontains=search) | Q(display_name__icontains=search))

    rows = []
    for symbol in queryset:
        snapshot = getattr(symbol, "snapshot", None)
        if snapshot is None:
            # A direction or numeric threshold requires an actual quote. Keep
            # no-data symbols visible for an unfiltered research scan, but do
            # not classify missing observations as gainers/losers or as passing
            # numeric filters.
            if direction != "all" or min_change is not None or max_change is not None or max_spread is not None:
                continue
            rows.append({"symbol": symbol.symbol, "display_name": symbol.display_name, "market": symbol.market, "sub_market": symbol.sub_market, "currency": symbol.currency, "status": "no_data", "source": "broker_snapshot_store"})
            continue
        change = Decimal(snapshot.change_percent or 0)
        spread = Decimal(snapshot.spread or 0)
        volume = Decimal(snapshot.volume or 0)
        if min_change is not None and change < min_change:
            continue
        if max_change is not None and change > max_change:
            continue
        if max_spread is not None and spread > max_spread:
            continue
        if direction == "gainers" and change <= 0:
            continue
        if direction == "losers" and change >= 0:
            continue
        rows.append({"symbol": symbol.symbol, "display_name": symbol.display_name, "market": symbol.market, "sub_market": symbol.sub_market, "currency": symbol.currency, "status": "ready", "source": "broker_snapshot_store", "last_price": str(snapshot.last_price), "bid": str(snapshot.bid) if snapshot.bid is not None else None, "ask": str(snapshot.ask) if snapshot.ask is not None else None, "spread": str(spread), "high": str(snapshot.high), "low": str(snapshot.low), "change": str(snapshot.change), "change_percent": str(change), "volume": str(volume), "timestamp": snapshot.timestamp.isoformat()})

    def key(row):
        if sort == "symbol":
            return row["symbol"].lower()
        if row["status"] != "ready":
            return Decimal("-Infinity")
        return Decimal(row[{"change_percent": "change_percent", "price": "last_price", "spread": "spread", "volume": "volume"}[sort]])
    rows.sort(key=key, reverse=sort != "symbol")
    try:
        limit = max(1, min(int(request.query_params.get("limit", 100)), 250))
    except (TypeError, ValueError):
        limit = 100
    return Response({"status": "ok", "source": "broker_snapshot_store", "count": min(len(rows), limit), "total_available": len(rows), "results": rows[:limit]})
