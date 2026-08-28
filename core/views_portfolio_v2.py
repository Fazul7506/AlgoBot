from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Avg
from django.shortcuts import render
from trading.models import Trade, PortfolioSnapshot
from apps.portfolio.models import Portfolio, PortfolioAllocation, PortfolioExposure, PortfolioPerformance, CashFlow


@login_required
def portfolio_center(request):
    portfolios = list(Portfolio.objects.filter(user=request.user).prefetch_related("allocations", "exposures", "performance"))
    snapshots = list(PortfolioSnapshot.objects.filter(user=request.user).order_by("created_at")[:120])
    trades = Trade.objects.filter(user=request.user)
    closed = trades.filter(status__in=["CLOSED", "ARCHIVED"])
    wins = closed.filter(profit__gt=0).count(); losses = closed.filter(profit__lt=0).count()
    net_pnl = closed.aggregate(v=Sum("profit"))["v"] or 0
    gross_profit = closed.filter(profit__gt=0).aggregate(v=Sum("profit"))["v"] or 0
    gross_loss = abs(closed.filter(profit__lt=0).aggregate(v=Sum("profit"))["v"] or 0)
    latest_performance = PortfolioPerformance.objects.filter(portfolio__user=request.user).order_by("-timestamp")[:20]
    exposures = PortfolioExposure.objects.filter(portfolio__user=request.user).order_by("-risk")[:30]
    allocations = PortfolioAllocation.objects.filter(portfolio__user=request.user).order_by("-allocated_capital")[:30]
    cashflows = CashFlow.objects.filter(portfolio__user=request.user).order_by("-timestamp")[:20]
    return render(request, "core/portfolio_center.html", {
        "portfolios": portfolios, "snapshots": snapshots, "latest_snapshot": snapshots[-1] if snapshots else None,
        "trade_count": trades.count(), "closed_count": closed.count(), "wins": wins, "losses": losses,
        "win_rate": (wins / max(wins + losses, 1)) * 100, "net_pnl": net_pnl,
        "profit_factor": gross_profit / gross_loss if gross_loss else (float(gross_profit) if gross_profit else 0),
        "latest_performance": latest_performance, "exposures": exposures, "allocations": allocations, "cashflows": cashflows,
    })


@login_required
def performance_center(request):
    snapshots = list(PortfolioSnapshot.objects.filter(user=request.user).order_by("created_at")[:250])
    performance = list(PortfolioPerformance.objects.filter(portfolio__user=request.user).order_by("-timestamp")[:100])
    trades = Trade.objects.filter(user=request.user); closed = trades.filter(status__in=["CLOSED", "ARCHIVED"])
    by_strategy = list(closed.values("strategy").annotate(trades=Count("id"), pnl=Sum("profit"), avg=Avg("profit")).order_by("-pnl")[:20])
    by_symbol = list(closed.values("symbol").annotate(trades=Count("id"), pnl=Sum("profit"), avg=Avg("profit")).order_by("-pnl")[:20])
    return render(request, "core/performance_center.html", {"snapshots": snapshots, "performance": performance, "by_strategy": by_strategy, "by_symbol": by_symbol, "closed_count": closed.count(), "net_pnl": closed.aggregate(v=Sum("profit"))["v"] or 0})


@login_required
def trade_postmortems(request):
    trades = list(Trade.objects.filter(user=request.user).select_related("strategy_fk").order_by("-opened_at")[:100])
    return render(request, "core/trade_postmortems.html", {"trades": trades})
