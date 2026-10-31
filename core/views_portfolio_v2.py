from django.contrib.auth.decorators import login_required
from collections import defaultdict

from django.db.models import Count, Q, Sum
from django.shortcuts import render

from apps.execution.models import BrokerTradeHistory, Order
from apps.market_data.services import MarketDataService
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
        "breakeven": known_pnl.filter(profit_loss=0).count(),
        "win_rate": (wins / known_count * 100) if known_count else None,
        "net_pnl": aggregate["net"] if known_count else None,
        "gross_profit": gross_profit,
        "gross_loss": abs(gross_loss),
        "profit_factor": (gross_profit / abs(gross_loss)) if gross_loss else None,
        "has_trade_pnl": known_count > 0,
        "known_count": known_count,
    }


@login_required
def portfolio_center(request):
    portfolios = list(Portfolio.objects.filter(user=request.user).prefetch_related("allocations", "exposures", "performance"))
    metrics = _settled_trade_metrics(request.user)
    latest_performance = PortfolioPerformance.objects.filter(portfolio__user=request.user).order_by("-timestamp")[:20]
    exposures = PortfolioExposure.objects.filter(portfolio__user=request.user).order_by("-risk")[:30]
    allocations = PortfolioAllocation.objects.filter(portfolio__user=request.user).order_by("-allocated_capital")[:30]
    cashflows = CashFlow.objects.filter(portfolio__user=request.user).order_by("-timestamp")[:20]
    return render(request, "portfolio/dashboard.html", {
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
    market_names = dict(MarketDataService.symbols.catalogue(active=None, tradable=None).filter(
        symbol__in=[row["symbol"] for row in by_symbol]
    ).values_list("symbol", "display_name"))
    for row in by_symbol:
        row["display_name"] = market_names.get(row["symbol"], "Market instrument") or "Market instrument"
    recent_trades = list(metrics["settled"].order_by("-settlement_time", "-broker_timestamp", "-id")[:8])
    average_win = metrics["gross_profit"] / metrics["wins"] if metrics["wins"] else None
    average_loss = metrics["gross_loss"] / metrics["losses"] if metrics["losses"] else None
    max_drawdown = max((abs(item.drawdown) for item in performance), default=None)
    # Attribute strategy results only when a broker trade reference exactly matches
    # an existing order's broker_reference; never estimate attribution from counts.
    broker_refs = set()
    for trade in metrics["known_pnl"].values("broker_order_id", "reference_id"):
        if trade["broker_order_id"]:
            broker_refs.add(trade["broker_order_id"])
        if trade["reference_id"]:
            broker_refs.add(trade["reference_id"])
    strategy_by_ref = {
        order.broker_reference: order.strategy
        for order in Order.objects.filter(user=request.user, broker_reference__in=broker_refs).exclude(strategy="")
    }
    strategy_totals = defaultdict(lambda: {"trades": 0, "pnl": 0})
    for trade in metrics["known_pnl"].values("broker_order_id", "reference_id", "profit_loss"):
        strategy = strategy_by_ref.get(trade["broker_order_id"]) or strategy_by_ref.get(trade["reference_id"])
        if strategy:
            strategy_totals[strategy]["trades"] += 1
            strategy_totals[strategy]["pnl"] += trade["profit_loss"]
    by_strategy = [
        {"strategy": name, "trades": values["trades"], "pnl": values["pnl"]}
        for name, values in strategy_totals.items()
    ]
    by_strategy.sort(key=lambda row: row["pnl"], reverse=True)
    duration_seconds = []
    for trade in metrics["settled"].exclude(duration__isnull=True).only("duration", "duration_unit"):
        value = float(trade.duration)
        unit = (trade.duration_unit or "s").lower()
        multiplier = {"s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "d": 86400}.get(unit)
        if multiplier:
            duration_seconds.append(value * multiplier)
    average_duration_seconds = sum(duration_seconds) / len(duration_seconds) if duration_seconds else None
    average_duration_label = None
    if average_duration_seconds is not None:
        total_seconds = int(round(average_duration_seconds))
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        average_duration_label = (f"{hours}h " if hours else "") + (f"{minutes}m " if minutes or hours else "") + f"{seconds}s"
    return render(request, "core/performance_center.html", {
        "snapshots": [],
        "performance": performance,
        "by_strategy": by_strategy,
        "by_symbol": by_symbol,
        "recent_trades": recent_trades,
        "closed_count": metrics["closed_count"],
        "trade_count": metrics["trade_count"],
        "known_count": metrics["known_count"],
        "wins": metrics["wins"],
        "losses": metrics["losses"],
        "breakeven": metrics["breakeven"],
        "win_rate": metrics["win_rate"],
        "net_pnl": metrics["net_pnl"],
        "gross_profit": metrics["gross_profit"],
        "gross_loss": metrics["gross_loss"],
        "profit_factor": metrics["profit_factor"],
        "average_win": average_win,
        "average_loss": average_loss,
        "max_drawdown": max_drawdown,
        "average_duration_seconds": average_duration_seconds,
        "average_duration_label": average_duration_label,
        "has_trade_pnl": metrics["has_trade_pnl"],
    })

@login_required
def trade_postmortems(request):
    trades = list(Order.objects.filter(user=request.user).select_related("broker_account").order_by("-created_at")[:100])
    market_names = dict(MarketDataService.symbols.catalogue(active=None, tradable=None).filter(
        symbol__in={trade.symbol for trade in trades if trade.symbol}
    ).values_list("symbol", "display_name"))
    for trade in trades:
        trade.display_name = market_names.get(trade.symbol, "Market instrument") or "Market instrument"
    return render(request, "core/trade_postmortems.html", {"trades": trades})
