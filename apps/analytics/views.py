from __future__ import annotations

import csv

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

from apps.analysis.advanced import analyze_candles
from apps.market_data.models import Candle, MarketSnapshot, MarketSymbol
from trading.models import PortfolioSnapshot, Trade

TIMEFRAME_MAP = {"M1": "1m", "M2": "2m", "M5": "5m", "M10": "10m", "M15": "15m", "M30": "30m", "H1": "1h", "H4": "4h", "D1": "1d", "1M": "1m", "5M": "5m", "15M": "15m", "30M": "30m", "1H": "1h", "4H": "4h"}


def _analytics_context(user):
    trades = Trade.objects.filter(user=user)
    snapshots = PortfolioSnapshot.objects.filter(user=user).order_by("-created_at")[:250]
    closed = trades.filter(status__in=["CLOSED", "ARCHIVED"])
    wins = closed.filter(profit__gt=0).count(); losses = closed.filter(profit__lt=0).count()
    gross_profit = closed.filter(profit__gt=0).aggregate(total=Sum("profit"))["total"] or 0
    gross_loss = abs(closed.filter(profit__lt=0).aggregate(total=Sum("profit"))["total"] or 0)
    return {"total_trades": trades.count(), "closed_trades": wins + losses, "winning_trades": wins, "losing_trades": losses, "win_rate": (wins / max(wins + losses, 1)) * 100, "profit_factor": gross_profit / gross_loss if gross_loss else (float(gross_profit) if gross_profit else 0), "average_profit": closed.aggregate(avg=Avg("profit"))["avg"] or 0, "net_pnl": closed.aggregate(total=Sum("profit"))["total"] or 0, "equity_curve": list(snapshots.values("created_at", "equity", "balance", "daily_pnl", "risk_utilization")), "strategy_distribution": list(trades.values("strategy").annotate(total=Count("id")).order_by("-total"))}


@login_required
def analytics_dashboard(request):
    return render(request, "analytics/dashboard.html", _analytics_context(request.user))


@login_required
def analysis_data(request):
    symbol = (request.GET.get("symbol") or "R_100").strip().upper()
    requested_tf = (request.GET.get("timeframe") or "M1").strip()
    timeframe = TIMEFRAME_MAP.get(requested_tf.upper(), requested_tf.lower())
    try: limit = min(max(int(request.GET.get("limit", 300)), 50), 1000)
    except (TypeError, ValueError): limit = 300
    market = MarketSymbol.objects.filter(symbol=symbol, is_active=True).first()
    if not market: return JsonResponse({"status": "error", "message": "Unknown or inactive market symbol."}, status=404)
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
    for trade in Trade.objects.filter(user=request.user).iterator(): writer.writerow([trade.symbol, trade.strategy, trade.status, trade.stake, trade.profit, trade.opened_at, trade.closed_at])
    return response
