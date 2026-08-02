from django.shortcuts import render

def dashboard(request): return render(request, "market_data/dashboard.html")
def symbols(request): return render(request, "market_data/symbols.html")
def symbol_detail(request, symbol): return render(request, "market_data/symbol_detail.html", {"symbol": symbol})
