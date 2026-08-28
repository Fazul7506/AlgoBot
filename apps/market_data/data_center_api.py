from datetime import timedelta

from django.db.models import Count, Max, Min
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Candle, MarketSymbol, Tick


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def quality(request):
    """Read-only data inventory and freshness telemetry for the research Data Center."""
    now = timezone.now()
    stale_after = now - timedelta(minutes=5)
    symbols = MarketSymbol.objects.filter(is_active=True).order_by("market", "symbol")
    rows = []
    for symbol in symbols:
        ticks = Tick.objects.filter(symbol=symbol).aggregate(
            count=Count("id"), first=Min("epoch"), last=Max("epoch"), latest_received=Max("received_at")
        )
        candle_count = Candle.objects.filter(symbol=symbol).count()
        frames = list(Candle.objects.filter(symbol=symbol).values_list("timeframe", flat=True).distinct())
        latest = ticks["latest_received"]
        age = None if latest is None else max(0, int((now - latest).total_seconds()))
        state = "no_data" if not ticks["count"] and not candle_count else ("stale" if latest and latest < stale_after else "healthy")
        rows.append({
            "symbol": symbol.symbol, "display_name": symbol.display_name, "market": symbol.market,
            "sub_market": symbol.sub_market, "tradable": symbol.is_tradable,
            "tick_count": ticks["count"], "tick_first_epoch": ticks["first"], "tick_last_epoch": ticks["last"],
            "latest_received_at": latest, "latest_age_seconds": age, "candle_count": candle_count,
            "candle_timeframes": frames, "status": state,
        })
    return Response({
        "status": "ok", "source": "backend_market_data_store", "generated_at": now,
        "summary": {
            "active_symbols": len(rows),
            "symbols_with_ticks": sum(bool(r["tick_count"]) for r in rows),
            "symbols_with_candles": sum(bool(r["candle_count"]) for r in rows),
            "total_ticks": Tick.objects.count(), "total_candles": Candle.objects.count(),
            "stale_ticks": Tick.objects.filter(received_at__lt=stale_after).count(),
            "freshness_window_seconds": 300,
        },
        "symbols": rows,
    })
