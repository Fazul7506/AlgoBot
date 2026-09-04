from __future__ import annotations

import csv

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

from apps.analysis.advanced import analyze_candles
from apps.execution.models import Order
from apps.market_data.models import Candle, MarketSnapshot, MarketSymbol
from apps.portfolio.models import PortfolioPerformance


def _order_profit(order):
    payload = order.broker_response or {}
    try:
        return float(payload.get("profit", payload.get("pnl", 0)) or 0)
    except (TypeError, ValueError):
        return 0.0


def _analytics_context(user):
    trades = Order.objects.filter(user=user)
    closed = trades.filter(status="executed")
    profits = [_order_profit(order) for order in closed]
    wins = sum(value > 0 for value in profits)
    losses = sum(value < 0 for value in profits)
    gross_profit = sum(value for value in profits if value > 0)
    gross_loss = abs(sum(value for value in profits if value < 0))
    strategy_distribution = list(trades.values("strategy").annotate(total=Count("id")).order_by("-total"))
    performance = PortfolioPerformance.objects.filter(portfolio__user=user).order_by("timestamp")[:250]
    equity_curve = [{"timestamp": item.timestamp, "equity": item.portfolio.equity, "balance": item.portfolio.current_balance, "daily_pnl": item.daily_return, "risk_utilization": item.drawdown} for item in performance]
    return {
        "total_trades": trades.count(), "closed_trades": wins + losses,
        "winning_trades": wins, "losing_trades": losses,
        "win_rate": (wins / max(wins + losses, 1)) * 100,
        "profit_factor": gross_profit / gross_loss if gross_loss else (float(gross_profit) if gross_profit else 0),
        "average_profit": (sum(profits) / len(profits)) if profits else 0,
        "net_pnl": sum(profits), "equity_curve": equity_curve,
        "strategy_distribution": strategy_distribution,
    }


@login_required
def analytics_dashboard(request):
    return render(request, "analytics/dashboard.html", _analytics_context(request.user))


@login_required
def analysis_data(request):
    symbol = (request.GET.get("symbol") or "R_100").strip().upper()
    timeframe = (request.GET.get("timeframe") or "M1").strip().upper()
    try:
        limit = min(max(int(request.GET.get("limit", 300)), 50), 1000)
    except (TypeError, ValueError):
        limit = 300
    market = MarketSymbol.objects.filter(symbol=symbol, is_active=True).first()
    if not market:
        return JsonResponse({"status": "error", "message": "Unknown or inactive market symbol."}, status=404)
    candles = list(Candle.objects.filter(symbol=market, timeframe=timeframe).order_by("-epoch")[:limit]); candles.reverse()
    payload = [{"open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume, "epoch": c.epoch} for c in candles]
    result = analyze_candles(payload, symbol=symbol, timeframe=timeframe)
    snapshot = MarketSnapshot.objects.filter(symbol=market).first()
    result["snapshot"] = {"last_price": float(snapshot.last_price), "bid": float(snapshot.bid) if snapshot and snapshot.bid is not None else None, "ask": float(snapshot.ask) if snapshot and snapshot.ask is not None else None, "change_percent": float(snapshot.change_percent)} if snapshot else None
    return JsonResponse(result)


@login_required
def analysis_markets(request):
    symbols = list(MarketSymbol.objects.filter(is_active=True, is_tradable=True).values("symbol", "display_name", "market", "sub_market").order_by("market", "symbol"))
    return JsonResponse({"markets": symbols})


@login_required
def analytics_export(request):
    response = HttpResponse(content_type="text/csv"); response["Content-Disposition"] = 'attachment; filename="trading-analytics.csv"'; writer = csv.writer(response)
    writer.writerow(["symbol", "strategy", "status", "stake", "profit", "opened_at", "closed_at"])
    for order in Order.objects.filter(user=request.user).iterator():
        writer.writerow([order.symbol, order.strategy, order.status, order.stake, _order_profit(order), order.created_at, order.updated_at if order.status == "executed" else None])
    return response
