from django.core.cache import cache
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from trading.models.core import Signal


SIGNALS_CACHE_KEY = "algobot:strategy_signals:v1"
SIGNALS_CACHE_TTL = 10


@login_required
def strategy_signals(request):
    """Fast authenticated read-only strategy-signal feed.

    Signals are backend records and do not require a broker round-trip. Keep
    this endpoint independent from broker/account synchronization so a Deriv
    latency issue cannot block the Signals page.
    """
    try:
        limit = min(max(int(request.GET.get("limit", 50)), 1), 100)
    except (TypeError, ValueError):
        limit = 50

    cache_key = f"{SIGNALS_CACHE_KEY}:{limit}"
    payload = cache.get(cache_key)
    if payload is None:
        rows = list(
            Signal.objects.order_by("-created_at")[:limit].values(
                "id",
                "symbol",
                "direction",
                "confidence",
                "market_regime",
                "strategy",
                "was_executed",
                "created_at",
            )
        )
        payload = {
            "status": "success",
            "count": len(rows),
            "data": rows,
        }
        cache.set(cache_key, payload, SIGNALS_CACHE_TTL)

    return JsonResponse(payload)
