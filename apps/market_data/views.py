from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@login_required
def dashboard(request):
    return render(request, "market_data/dashboard.html")

@login_required
def symbols(request):
    return render(request, "market_data/symbols.html")

@login_required
def symbol_detail(request, symbol):
    return render(request, "market_data/symbol_detail.html", {"symbol": symbol})
