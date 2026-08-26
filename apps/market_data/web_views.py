from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from .models import MarketSymbol
from .serializers import MarketSymbolSerializer


CATALOGUE_CACHE_KEY = "algobot:market_catalogue:deriv:v2"
CATALOGUE_CACHE_TTL = 300


@login_required
def market_catalogue(request):
    """Return the broker-synced Deriv catalogue without blocking on Deriv.

    The catalogue is persisted by the broker sync process, so this endpoint
    never opens a broker connection. A short server-side cache prevents the
    Markets and Trading pages from repeatedly serializing the full catalogue.
    """
    cached = cache.get(CATALOGUE_CACHE_KEY)
    if cached is not None:
        return JsonResponse(cached)

    queryset = MarketSymbol.objects.filter(
        broker="deriv", is_active=True, is_tradable=True
    ).order_by("market", "symbol")
    symbols = MarketSymbolSerializer(queryset, many=True).data
    payload = {
        "status": "ok",
        "source": "backend_market_catalogue",
        "symbols": symbols,
        "count": len(symbols),
    }
    cache.set(CATALOGUE_CACHE_KEY, payload, CATALOGUE_CACHE_TTL)
    return JsonResponse(payload)
