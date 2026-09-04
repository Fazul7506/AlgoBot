from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Avg
from django.shortcuts import render

from apps.execution.models import Order
from apps.portfolio.models import Portfolio, PortfolioAllocation, PortfolioExposure, PortfolioPerformance, CashFlow


@login_required
def portfolio_center(request):
    portfolios = list(Portfolio.objects.filter(user=request.user).prefetch_related("allocations", "exposures", "performance"))
    trades = Order.objects.filter(user=request.user)
    closed = trades.filter(status="executed")
    wins = 0
    losses = 0
    net_pnl = 0
    gross_profit = 0
    gross_loss = 0
    latest_performance = PortfolioPerformance.objects.filter(portfolio__user=request.user).order_by("-timestamp")[:20]
    exposures = PortfolioExposure.objects.filter(portfolio__user=request.user).order_by("-risk")[:30]
    allocations = PortfolioAllocation.objects.filter(portfolio__user=request.user).order_by("-allocated_capital")[:30]
    cashflows = CashFlow.objects.filter(portfolio__user=request.user).order_by("-timestamp")[:20]
    return render(request, "core/portfolio_center.html", {
        "portfolios": portfolios, "snapshots": [], "latest_snapshot": None,
        "trade_count": trades.count(), "closed_count": closed.count(), "wins": wins, "losses": losses,
        "win_rate": 0, "net_pnl": net_pnl,
        "profit_factor": gross_profit / gross_loss if gross_loss else 0,
        "latest_performance": latest_performance, "exposures": exposures, "allocations": allocations, "cashflows": cashflows,
    })


@login_required
def performance_center(request):
    performance = list(PortfolioPerformance.objects.filter(portfolio__user=request.user).order_by("-timestamp")[:100])
    trades = Order.objects.filter(user=request.user)
    closed = trades.filter(status="executed")
    by_strategy = list(closed.values("strategy").annotate(trades=Count("id")).order_by("-trades")[:20])
    by_symbol = list(closed.values("symbol").annotate(trades=Count("id")).order_by("-trades")[:20])
    return render(request, "core/performance_center.html", {
        "snapshots": [], "performance": performance, "by_strategy": by_strategy,
        "by_symbol": by_symbol, "closed_count": closed.count(), "net_pnl": 0,
    })


@login_required
def trade_postmortems(request):
    trades = list(Order.objects.filter(user=request.user).order_by("-created_at")[:100])
    return render(request, "core/trade_postmortems.html", {"trades": trades})
