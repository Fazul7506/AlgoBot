from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.shortcuts import render

from apps.execution.models import BrokerTradeHistory, Order
from apps.portfolio.models import Portfolio, PortfolioAllocation, PortfolioExposure, PortfolioPerformance, CashFlow


CLOSED_TRADE_STATUSES = ("sold", "expired", "closed", "won", "lost", "settled")


def _settled_trade_metrics(user):
    history = BrokerTradeHistory.objects.filter(user=user)
    settled = history.filter(Q(settlement_time__isnull=False) | Q(status__in=CLOSED_TRADE_STATUSES))
    known_pnl = settled.filter(profit_loss__isnull=False)
    aggregate = known_pnl.aggregate(net=Sum("profit_loss"))
    gross_profit = known_pnl.filter(profit_loss__gt=0).aggregate(total=Sum("profit_loss"))["total"] or 0
    gross_loss = known_pnl.filter(profit_loss__lt=0).aggregate(total=Sum("profit_loss"))["total"] or 0
    wins = known_pnl.filter(profit_loss__gt=0).count()
    losses = known_pnl.filter(profit_loss__lt=0).count()
    known_count = known_pnl.count()
    return {
        "history": history,
        "settled": settled,
        "known_pnl": known_pnl,
        "trade_count": history.count(),
        "closed_count": settled.count(),
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / known_count * 100) if known_count else None,
        "net_pnl": aggregate["net"] if known_count else None,
        "gross_profit": gross_profit,
        "gross_loss": abs(gross_loss),
        "profit_factor": (gross_profit / abs(gross_loss)) if gross_loss else None,
        "has_trade_pnl": known_count > 0,
    }


@login_required
def portfolio_center(request):
    portfolios = list(Portfolio.objects.filter(user=request.user).prefetch_related("allocations", "exposures", "performance"))
    metrics = _settled_trade_metrics(request.user)
    latest_performance = PortfolioPerformance.objects.filter(portfolio__user=request.user).order_by("-timestamp")[:20]
    exposures = PortfolioExposure.objects.filter(portfolio__user=request.user).order_by("-risk")[:30]
    allocations = PortfolioAllocation.objects.filter(portfolio__user=request.user).order_by("-allocated_capital")[:30]
    cashflows = CashFlow.objects.filter(portfolio__user=request.user).order_by("-timestamp")[:20]
    return render(request, "core/portfolio_center.html", {
        "portfolios": portfolios,
        "snapshots": [],
        "latest_snapshot": None,
        **{key: metrics[key] for key in ("trade_count", "closed_count", "wins", "losses", "win_rate", "net_pnl", "profit_factor", "has_trade_pnl")},
        "latest_performance": latest_performance,
        "exposures": exposures,
        "allocations": allocations,
        "cashflows": cashflows,
    })


@login_required
def performance_center(request):
    metrics = _settled_trade_metrics(request.user)
    performance = list(PortfolioPerformance.objects.filter(portfolio__user=request.user).order_by("-timestamp")[:100])
    by_symbol = list(
        metrics["known_pnl"].values("symbol").annotate(trades=Count("id"), pnl=Sum("profit_loss")).order_by("-trades")[:20]
    )
    # Broker trade history does not have a canonical strategy association, so do
    # not infer strategy P/L from order counts.
    return render(request, "core/performance_center.html", {
        "snapshots": [],
        "performance": performance,
        "by_strategy": [],
        "by_symbol": by_symbol,
        "closed_count": metrics["closed_count"],
        "net_pnl": metrics["net_pnl"],
        "has_trade_pnl": metrics["has_trade_pnl"],
    })


@login_required
def trade_postmortems(request):
    trades = list(Order.objects.filter(user=request.user).select_related("broker_account").order_by("-created_at")[:100])
    return render(request, "core/trade_postmortems.html", {"trades": trades})
