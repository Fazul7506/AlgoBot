from __future__ import annotations

import csv
from django.db.models import Avg, Count, Sum
from django.http import HttpResponse
from django.shortcuts import render
from trading.models import PerformanceSnapshot, Trade


def _analytics_context(user=None):
    trades = Trade.objects.all()
    snapshots = PerformanceSnapshot.objects.all()[:250]
    if user and user.is_authenticated:
        trades = trades.filter(user=user)
        snapshots = snapshots.filter(user=user)
    closed = trades.filter(status__in=["CLOSED", "ARCHIVED"])
    wins = closed.filter(profit__gt=0).count()
    losses = closed.filter(profit__lt=0).count()
    gross_profit = closed.filter(profit__gt=0).aggregate(total=Sum("profit"))["total"] or 0
    gross_loss = abs(closed.filter(profit__lt=0).aggregate(total=Sum("profit"))["total"] or 0)
    return {
        "total_trades": trades.count(),
        "win_rate": (wins / max(wins + losses, 1)) * 100,
        "profit_factor": gross_profit / gross_loss if gross_loss else gross_profit,
        "average_profit": closed.aggregate(avg=Avg("profit"))["avg"] or 0,
        "equity_curve": list(snapshots.values("created_at", "equity", "balance", "drawdown_pct")),
        "strategy_distribution": list(trades.values("strategy").annotate(total=Count("id"))),
    }


def analytics_dashboard(request):
    return render(request, "analytics/dashboard.html", _analytics_context(request.user))


def analytics_export(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="trading-analytics.csv"'
    writer = csv.writer(response)
    writer.writerow(["symbol", "strategy", "status", "stake", "profit", "opened_at", "closed_at"])
    trades = Trade.objects.all()
    if request.user.is_authenticated:
        trades = trades.filter(user=request.user)
    for trade in trades.iterator():
        writer.writerow([trade.symbol, trade.strategy, trade.status, trade.stake, trade.profit, trade.opened_at, trade.closed_at])
    return response
