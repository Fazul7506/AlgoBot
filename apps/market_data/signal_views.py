from django.core.cache import cache
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from apps.strategies.models import StrategySignal


SIGNALS_CACHE_KEY = "algobot:strategy_signals:v1"
SIGNALS_CACHE_TTL = 10


@login_required
def strategy_signals(request):
    """Fast authenticated read-only canonical strategy-signal feed."""
    try:
        limit = min(max(int(request.GET.get("limit", 50)), 1), 100)
    except (TypeError, ValueError):
        limit = 50

    cache_key = f"{SIGNALS_CACHE_KEY}:{limit}"
    payload = cache.get(cache_key)
    if payload is None:
        signals = StrategySignal.objects.select_related("strategy", "configuration").order_by("-timestamp")[:limit]
        rows = [
            {
                "id": signal.id,
                "symbol": signal.symbol,
                "direction": signal.signal,
                "confidence": signal.confidence,
                "market_regime": "",
                "strategy": signal.strategy.name,
                "was_executed": False,
                "created_at": signal.timestamp,
            }
            for signal in signals
        ]
        payload = {
            "status": "success",
            "count": len(rows),
            "data": rows,
        }
        cache.set(cache_key, payload, SIGNALS_CACHE_TTL)

    return JsonResponse(payload)
