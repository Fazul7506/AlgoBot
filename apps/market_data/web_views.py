from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import MarketSymbol
from .serializers import MarketSymbolSerializer


@login_required

def market_catalogue(request):
    """Browser-safe market catalogue endpoint.

    This endpoint intentionally lives outside /api/ so Cloudflare API/WAF rules
    cannot turn a normal authenticated catalogue read into an HTML challenge.
    It reads the authoritative broker-synced catalogue stored by Django.
    """
    queryset = MarketSymbol.objects.filter(
        broker="deriv", is_active=True, is_tradable=True
    ).order_by("market", "symbol")
    symbols = MarketSymbolSerializer(queryset, many=True).data
    return JsonResponse({
        "status": "ok",
        "source": "backend_market_catalogue",
        "symbols": symbols,
        "count": len(symbols),
    })
