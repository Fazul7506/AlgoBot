from __future__ import annotations

import csv
import hashlib
import json
import time

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

from apps.analysis.advanced import analyze_candles
from apps.execution.models import Order
from apps.market_data.models import MarketSnapshot, MarketSymbol
from apps.market_data.deriv_sync import fetch_contracts_for, fetch_tick
from apps.market_data.historical import fetch_and_store, fetch_and_store_ticks
from apps.market_data.constants import TIMEFRAMES
from apps.market_data.research_data import ResearchDataService
from apps.portfolio.models import PortfolioPerformance


ANALYTICS_CACHE_SECONDS = 15
ANALYSIS_CACHE_SECONDS = 3


def _order_profit(order):
    payload = order.broker_response or {}
    try:
        return float(payload.get("profit", payload.get("pnl", 0)) or 0)
    except (TypeError, ValueError):
        return 0.0


def _analysis_markets():
    cache_key = "algobot:analysis:markets:v1"
    markets = cache.get(cache_key)
    if markets is None:
        markets = list(MarketSymbol.objects.filter(is_active=True, is_tradable=True).values("symbol", "display_name", "market", "sub_market").order_by("market", "symbol"))
        cache.set(cache_key, markets, 60)
    return markets


def _analytics_context(user):
    cache_key = f"algobot:analytics:v2:{user.pk}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    trades = Order.objects.filter(user=user).only("id", "status", "broker_response", "strategy")
    closed = trades.filter(status="executed")
    profits = [_order_profit(order) for order in closed.iterator(chunk_size=250)]
    wins = sum(value > 0 for value in profits)
    losses = sum(value < 0 for value in profits)
    gross_profit = sum(value for value in profits if value > 0)
    gross_loss = abs(sum(value for value in profits if value < 0))
    strategy_distribution = list(
        trades.values("strategy").annotate(total=Count("id")).order_by("-total")
    )
    performance = (
        PortfolioPerformance.objects.filter(portfolio__user=user)
        .select_related("portfolio")
        .only(
            "timestamp",
            "daily_return",
            "drawdown",
            "portfolio__equity",
            "portfolio__current_balance",
        )
        .order_by("-timestamp")[:250]
    )
    performance = reversed(list(performance))
    equity_curve = [
        {
            "timestamp": item.timestamp,
            "equity": item.portfolio.equity,
            "balance": item.portfolio.current_balance,
            "daily_pnl": item.daily_return,
            "risk_utilization": item.drawdown,
        }
        for item in performance
    ]
    markets = _analysis_markets()
    context = {
        "total_trades": trades.count(),
        "closed_trades": wins + losses,
        "winning_trades": wins,
        "losing_trades": losses,
        "win_rate": (wins / max(wins + losses, 1)) * 100,
        "profit_factor": gross_profit / gross_loss if gross_loss else (float(gross_profit) if gross_profit else 0),
        "average_profit": (sum(profits) / len(profits)) if profits else 0,
        "net_pnl": sum(profits),
        "equity_curve": equity_curve,
        "strategy_distribution": strategy_distribution,
        "analysis_markets_json": json.dumps(markets),
    }
    cache.set(cache_key, context, ANALYTICS_CACHE_SECONDS)
    return context


@login_required
def analytics_dashboard(request):
    return render(request, "analytics/dashboard.html", _analytics_context(request.user))


@login_required
def analysis_data(request):
    symbol = (request.GET.get("symbol") or "R_100").strip().upper()
    timeframe = (request.GET.get("timeframe") or "1m").strip()
    try:
        limit = min(max(int(request.GET.get("limit", 300)), 50), 1000)
    except (TypeError, ValueError):
        limit = 300

    refresh_requested = str(request.GET.get("refresh", "1")).lower() in {"1", "true", "yes"}
    cache_key = "algobot:analysis:v4:" + hashlib.sha256(
        json.dumps([
            request.user.pk,
            symbol,
            timeframe.lower(),
            limit,
            bool(refresh_requested),
        ]).encode("utf-8")
    ).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse(cached)

    research_data = ResearchDataService()
    try:
        canonical_timeframe = research_data.timeframe(timeframe)
        market = research_data.market(symbol)
    except ValueError as exc:
        return JsonResponse({"status": "error", "message": str(exc)}, status=404)

    refresh_result = None
    if refresh_requested:
        try:
            if canonical_timeframe == "tick" or TIMEFRAMES[canonical_timeframe] < 60:
                refresh_result = fetch_and_store_ticks(market.symbol, count=min(max(limit, 50), 1000))
            else:
                refresh_result = fetch_and_store(market.symbol, canonical_timeframe, count=min(max(limit, 50), 1000))
            live_tick = fetch_tick(market.symbol)
            from apps.market_data.services import MarketDataService
            MarketDataService().tick_service.ingest(live_tick)
        except Exception as exc:
            return JsonResponse(
                {
                    "status": "error",
                    "code": "BROKER_DATA_REFRESH_FAILED",
                    "message": "Fresh Deriv market data could not be confirmed; stale research data was not substituted.",
                    "detail": str(exc),
                    "symbol": market.symbol,
                    "timeframe": canonical_timeframe,
                },
                status=503,
            )

    candles = research_data.candles(market.symbol, canonical_timeframe, limit=limit)

    if not candles:
        return JsonResponse(
            {
                "status": "error",
                "message": "No persisted market candles are available for this symbol/timeframe.",
                "source": "market_data.Candle",
                "symbol": market.symbol,
                "timeframe": canonical_timeframe,
            },
            status=503,
        )

    result = analyze_candles(candles, symbol=market.symbol, timeframe=canonical_timeframe)
    snapshot = MarketSnapshot.objects.filter(symbol=market).only("last_price", "bid", "ask", "change_percent").first()
    if refresh_requested:
        # The live broker tick is the authoritative current price. The stored
        # snapshot remains useful for bid/ask/change context, but must never
        # override the current broker quote in Analysis.
        try:
            live_tick
        except UnboundLocalError:
            live_tick = None
        if live_tick and live_tick.get("quote") is not None:
            result["price"] = float(live_tick["quote"])
    result["snapshot"] = (
        {
            "last_price": float(snapshot.last_price),
            "bid": float(snapshot.bid) if snapshot.bid is not None else None,
            "ask": float(snapshot.ask) if snapshot.ask is not None else None,
            "change_percent": float(snapshot.change_percent),
        }
        if snapshot
        else None
    )
    latest_epoch = int(candles[-1]["epoch"])
    age_seconds = max(0, int(time.time()) - latest_epoch)
    result["data_provenance"] = {
        "source": "market_data.Candle",
        "broker": "Deriv",
        "storage": "database",
        "refresh_requested": refresh_requested,
        "refresh_result": refresh_result,
        "symbol": market.symbol,
        "timeframe": canonical_timeframe,
        "candle_count": len(candles),
        "first_epoch": candles[0]["epoch"],
        "last_epoch": latest_epoch,
        "age_seconds": age_seconds,
        "fresh": age_seconds <= max(120, TIMEFRAMES[canonical_timeframe] * 2),
        "candle_source": "deriv_candles" if TIMEFRAMES[canonical_timeframe] >= 60 else "tick_stream",
    }
    cache.set(cache_key, result, ANALYSIS_CACHE_SECONDS)
    return JsonResponse(result)


@login_required
def analysis_markets(request):
    return JsonResponse({"markets": _analysis_markets()})


@login_required
def analysis_contracts(request):
    symbol = (request.GET.get("symbol") or "").strip().upper()
    if not symbol:
        return JsonResponse({"status": "error", "code": "SYMBOL_REQUIRED", "message": "A market symbol is required."}, status=400)
    try:
        market = MarketSymbol.objects.get(symbol=symbol, is_active=True, is_tradable=True)
    except MarketSymbol.DoesNotExist:
        return JsonResponse({"status": "error", "code": "MARKET_UNAVAILABLE", "message": "The selected market is not currently available from the broker catalogue."}, status=404)
    try:
        capabilities = fetch_contracts_for(market.symbol)
    except Exception as exc:
        return JsonResponse(
            {
                "status": "error",
                "code": "BROKER_CONTRACT_DATA_FAILED",
                "message": "Deriv contract capabilities could not be confirmed.",
                "detail": str(exc),
                "symbol": market.symbol,
            },
            status=503,
        )
    return JsonResponse(
        {
            "status": "ok",
            "broker": "Deriv",
            "symbol": market.symbol,
            "display_name": market.display_name,
            "market": market.market,
            "sub_market": market.sub_market,
            "capabilities": capabilities,
        }
    )


@login_required
def analysis_contracts(request):
    symbol = (request.GET.get("symbol") or "").strip().upper()
    if not symbol:
        return JsonResponse({"status": "error", "code": "SYMBOL_REQUIRED", "message": "A market symbol is required."}, status=400)
    try:
        market = MarketSymbol.objects.get(symbol=symbol, is_active=True, is_tradable=True)
    except MarketSymbol.DoesNotExist:
        return JsonResponse({"status": "error", "code": "MARKET_UNAVAILABLE", "message": "The selected market is not currently available from the broker catalogue."}, status=404)
    try:
        capabilities = fetch_contracts_for(market.symbol)
    except Exception as exc:
        return JsonResponse(
            {
                "status": "error",
                "code": "BROKER_CONTRACT_DATA_FAILED",
                "message": "Deriv contract capabilities could not be confirmed.",
                "detail": str(exc),
                "symbol": market.symbol,
            },
            status=503,
        )
    return JsonResponse(
        {
            "status": "ok",
            "broker": "Deriv",
            "symbol": market.symbol,
            "display_name": market.display_name,
            "market": market.market,
            "sub_market": market.sub_market,
            "capabilities": capabilities,
        }
    )


@login_required
def analytics_export(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="trading-analytics.csv"'
    writer = csv.writer(response)
    writer.writerow(["symbol", "strategy", "status", "stake", "profit", "opened_at", "closed_at"])
    for order in Order.objects.filter(user=request.user).iterator(chunk_size=250):
        writer.writerow(
            [
                order.symbol,
                order.strategy,
                order.status,
                order.stake,
                _order_profit(order),
                order.created_at,
                order.updated_at if order.status == "executed" else None,
            ]
        )
    return response
