from __future__ import annotations

import csv
from django.db.models import Avg, Count, Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from trading.models import PortfolioSnapshot, Trade


def _analytics_context(user):
    trades = Trade.objects.filter(user=user)
    snapshots = PortfolioSnapshot.objects.filter(user=user).order_by("-created_at")[:250]
    closed = trades.filter(status__in=["CLOSED", "ARCHIVED"])
    wins = closed.filter(profit__gt=0).count()
    losses = closed.filter(profit__lt=0).count()
    gross_profit = closed.filter(profit__gt=0).aggregate(total=Sum("profit"))["total"] or 0
    gross_loss = abs(closed.filter(profit__lt=0).aggregate(total=Sum("profit"))["total"] or 0)
    equity_curve = list(
        snapshots.values("created_at", "equity", "balance", "daily_pnl", "risk_utilization")
    )
    return {
        "total_trades": trades.count(),
        "closed_trades": wins + losses,
        "winning_trades": wins,
        "losing_trades": losses,
        "win_rate": (wins / max(wins + losses, 1)) * 100,
        "profit_factor": gross_profit / gross_loss if gross_loss else (float(gross_profit) if gross_profit else 0),
        "average_profit": closed.aggregate(avg=Avg("profit"))["avg"] or 0,
        "net_pnl": closed.aggregate(total=Sum("profit"))["total"] or 0,
        "equity_curve": equity_curve,
        "strategy_distribution": list(
            trades.values("strategy").annotate(total=Count("id")).order_by("-total")
        ),
    }


@login_required
def analytics_dashboard(request):
    return render(request, "analytics/dashboard.html", _analytics_context(request.user))


@login_required
def analytics_export(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="trading-analytics.csv"'
    writer = csv.writer(response)
    writer.writerow(["symbol", "strategy", "status", "stake", "profit", "opened_at", "closed_at"])
    for trade in Trade.objects.filter(user=request.user).iterator():
        writer.writerow(
            [trade.symbol, trade.strategy, trade.status, trade.stake, trade.profit, trade.opened_at, trade.closed_at]
        )
    return response
