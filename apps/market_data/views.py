from django.contrib.auth.decorators import login_required
import logging
from django.http import JsonResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)

from .models import MarketSymbol

BACKFILL_COUNT = 5000


def dashboard(request):
    return render(request, "market_data/dashboard.html")


@login_required
def symbols(request):
    return render(request, "market_data/symbols.html")


@login_required
def symbol_detail(request, symbol):
    return render(request, "market_data/symbol_detail.html", {"symbol": symbol})
