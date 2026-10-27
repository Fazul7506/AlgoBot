"""Account-scoped Signals workspace read API.

This endpoint intentionally exposes only persisted signal facts. Performance outcomes
and sentiment are marked unavailable when the source records do not contain them.
"""
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import logging

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.market_data.models import MarketSymbol
from apps.strategies.models import StrategySignal
from core.account_context import get_active_account

log = logging.getLogger(__name__)
HIGH_CONFIDENCE_THRESHOLD = Decimal("70")


def _metadata(row):
    if isinstance(row, dict):
        return row.get("metadata", row)
    return row.metadata if isinstance(getattr(row, "metadata", None), dict) else {}


def _classification(row):
    metadata = _metadata(row)
    raw = metadata.get("strategy_category") or metadata.get("classification") or getattr(row.strategy, "category", "")
    value = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if "scalp" in value:
        return "scalping"
    if "swing" in value:
        return "swing"
    if "intra" in value or value in {"day", "day_trading"}:
        return "intraday"
    return value or "unknown"


def _lifecycle(row):
    metadata = _metadata(row)
    return str(metadata.get("lifecycle") or metadata.get("lifecycle_state") or metadata.get("status") or "unknown").lower()


def _decimal(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _serialize(row, market_lookup):
    metadata = _metadata(row)
    market = market_lookup.get(row.symbol)
    category = _classification(row)
    direction = str(metadata.get("direction") or row.signal or "").upper()
    return {
        "id": row.pk,
        "symbol": row.symbol,
        "display_name": getattr(market, "display_name", None) or metadata.get("display_name") or row.symbol,
        "market": getattr(market, "market", None) or metadata.get("market_type") or metadata.get("market") or "Unclassified",
        "direction": direction if direction in {"BUY", "SELL"} else None,
        "strategy": row.strategy.name,
        "strategy_category": category,
        "entry_price": str(row.entry_price) if row.entry_price is not None else None,
        "take_profit": str(row.take_profit) if row.take_profit is not None else None,
        "stop_loss": str(row.stop_loss) if row.stop_loss is not None else None,
        "confidence": str(row.confidence) if row.confidence is not None else None,
        "status": _lifecycle(row),
        "created_at": row.timestamp.isoformat(),
        "metadata_outcome": metadata.get("outcome") or metadata.get("result"),
    }


def _matches_category(row, category):
    if not category or category == "all":
        return True
    if category == "high_confidence":
        return row.confidence is not None and row.confidence >= HIGH_CONFIDENCE_THRESHOLD
    return _classification(row) == category


def _outcome_stats(rows):
    wins = losses = breakeven = 0
    realized = []
    for row in rows:
        meta = _metadata(row)
        outcome = str(meta.get("outcome") or meta.get("result") or "").strip().lower()
        lifecycle = str(meta.get("lifecycle") or meta.get("lifecycle_state") or meta.get("status") or "").strip().lower()
        if lifecycle in {"active", "open", "pending", "live", "actionable", "created", "validated", "waiting"} or outcome in {"active", "open", "pending", "live", "actionable"}:
            continue
        pnl = _decimal(meta.get("realized_pnl", meta.get("pnl")))
        if outcome in {"win", "won", "winning", "take_profit"} or (pnl is not None and pnl > 0):
            wins += 1
        elif outcome in {"loss", "lost", "losing", "stop_loss"} or (pnl is not None and pnl < 0):
            losses += 1
        elif outcome in {"breakeven", "break_even", "flat"} or (pnl is not None and pnl == 0):
            breakeven += 1
        if pnl is not None and (outcome or meta.get("realized_pnl") is not None):
            realized.append(pnl)
    completed = wins + losses + breakeven
    gross_profit = sum((p for p in realized if p > 0), Decimal("0"))
    gross_loss = sum((p for p in realized if p < 0), Decimal("0"))
    profit_factor = (gross_profit / abs(gross_loss)) if gross_loss else None
    return {
        "wins": wins, "losses": losses, "breakeven": breakeven,
        "completed": completed,
        "win_rate": round(wins * 100 / completed, 2) if completed else None,
        "realized_pnl": str(sum(realized, Decimal("0"))) if realized else None,
        "average_profit": str(gross_profit / sum(1 for value in realized if value > 0)) if any(value > 0 for value in realized) else None,
        "average_loss": str(gross_loss / sum(1 for value in realized if value < 0)) if any(value < 0 for value in realized) else None,
        "profit_factor": str(profit_factor) if profit_factor is not None else None,
        "performance_available": bool(realized or completed),
    }


@login_required
@require_GET
def signals_workspace_api(request):
    """Return server-filtered, stable, paginated signals for the active account."""
    account = get_active_account(request.user, request=request)
    if account is None:
        return JsonResponse({
            "status": "unavailable", "message": "Connect or select an authorized broker account to view account-scoped signals.",
            "signals": [], "count": 0, "page": 1, "pages": 0,
            "metrics": None, "performance": None, "sentiment": {"status": "unavailable", "reason": "No authorized account"},
        }, status=409)

    try:
        page = max(1, min(int(request.GET.get("page", "1")), 1000000))
        page_size = max(1, min(int(request.GET.get("page_size", "10")), 50))
    except (TypeError, ValueError):
        return JsonResponse({"status": "error", "message": "page and page_size must be integers."}, status=400)

    now = timezone.now()
    base = StrategySignal.objects.select_related("strategy", "configuration").filter(
        configuration__user=request.user,
        configuration__broker_account=account,
        configuration__is_active=True,
        configuration__enabled=True,
        strategy__enabled=True,
        timestamp__lte=now,
    )
    symbol = str(request.GET.get("asset") or "").strip()[:40]
    market = str(request.GET.get("market") or "").strip()[:80]
    category = str(request.GET.get("category") or "all").strip().lower()
    if symbol:
        base = base.filter(symbol=symbol)
    search = str(request.GET.get("q") or "").strip()[:100]
    if search:
        base = base.filter(Q(symbol__icontains=search) | Q(strategy__name__icontains=search) | Q(strategy__category__icontains=search) | Q(metadata__display_name__icontains=search))
    if market:
        matching_symbols = MarketSymbol.objects.filter(is_active=True, market__iexact=market).values_list("symbol", flat=True)
        base = base.filter(Q(symbol__in=matching_symbols) | Q(metadata__market_type__iexact=market) | Q(metadata__market__iexact=market))

    detail_id = str(request.GET.get("detail_id") or "").strip()
    if detail_id:
        if not detail_id.isdigit():
            return JsonResponse({"status": "error", "message": "Invalid signal identifier."}, status=400)
        detail_row = base.filter(pk=int(detail_id)).select_related("strategy", "configuration").first()
        if detail_row is None:
            return JsonResponse({"status": "error", "message": "Signal not found for the selected authorized account."}, status=404)
        detail_market = MarketSymbol.objects.filter(symbol=detail_row.symbol).only("symbol", "display_name", "market").first()
        return JsonResponse({"status": "success", "detail": _serialize(detail_row, {detail_row.symbol: detail_market} if detail_market else {})})

    # Keep table rows paginated in SQL and compute counts without materializing the
    # full signal queryset. Legacy outcome metadata is streamed in bounded chunks.
    def category_queryset(key):
        if key == "all":
            return base
        if key == "high_confidence":
            return base.filter(confidence__gte=HIGH_CONFIDENCE_THRESHOLD)
        if key == "scalping":
            return base.filter(Q(strategy__category__icontains="scalping") | Q(metadata__strategy_category__icontains="scalp") | Q(metadata__classification__icontains="scalp"))
        if key == "swing":
            return base.filter(Q(strategy__category__icontains="swing") | Q(metadata__strategy_category__icontains="swing") | Q(metadata__classification__icontains="swing"))
        if key == "intraday":
            return base.filter(Q(metadata__strategy_category__icontains="intraday") | Q(metadata__classification__icontains="intraday"))
        return base.none()

    category_counts = {key: category_queryset(key).count() for key in ("all", "high_confidence", "scalping", "intraday", "swing")}
    filtered_qs = category_queryset(category if category in category_counts else "all")
    total = filtered_qs.count()
    pages = (total + page_size - 1) // page_size
    if pages and page > pages:
        page = pages
    start = (page - 1) * page_size
    page_rows = list(filtered_qs.select_related("strategy", "configuration").order_by("-timestamp", "-pk")[start:start + page_size])
    market_lookup = {m.symbol: m for m in MarketSymbol.objects.filter(symbol__in=[r.symbol for r in page_rows]).only("symbol", "display_name", "market")}

    recent_start = now - timedelta(days=7)
    prior_start = now - timedelta(days=14)
    active_states = ["active", "actionable", "open", "live", "confirmed"]
    active_q = (Q(metadata__lifecycle__in=active_states) | Q(metadata__lifecycle_state__in=active_states) | Q(metadata__status__in=active_states))
    active_count = base.filter(active_q).count()
    active_recent = base.filter(timestamp__gte=recent_start).filter(active_q).count()
    active_prior = base.filter(timestamp__gte=prior_start, timestamp__lt=recent_start).filter(active_q).count()
    last_week_count = base.filter(timestamp__gte=recent_start).count()
    prior_week_count = base.filter(timestamp__gte=prior_start, timestamp__lt=recent_start).count()
    trend_counts = [base.filter(timestamp__date=(now.date() - timedelta(days=day))).count() for day in range(6, -1, -1)]
    trend_active = [base.filter(timestamp__date=(now.date() - timedelta(days=day))).filter(active_q).count() for day in range(6, -1, -1)]

    def outcomes_for(queryset):
        rows = ({"metadata": meta} for meta in queryset.values_list("metadata", flat=True).iterator(chunk_size=500))
        return _outcome_stats(rows)

    outcomes = outcomes_for(base)
    current_outcomes = outcomes_for(base.filter(timestamp__gte=recent_start))
    prior_outcomes = outcomes_for(base.filter(timestamp__gte=prior_start, timestamp__lt=recent_start))
    daily_win_rates = []
    daily_profit_factors = []
    for day in range(6, -1, -1):
        day_qs = base.filter(timestamp__date=(now.date() - timedelta(days=day)))
        daily = outcomes_for(day_qs)
        daily_win_rates.append(daily["win_rate"])
        daily_profit_factors.append(daily["profit_factor"])
    latest = base.order_by("-timestamp", "-pk").values_list("timestamp", flat=True).first()
    metrics = {
        "total_signals": category_counts["all"],
        "total_signals_change": last_week_count - prior_week_count,
        "active_signals": active_count,
        "active_signals_change": active_recent - active_prior,
        "high_confidence_threshold": str(HIGH_CONFIDENCE_THRESHOLD),
        "win_rate": outcomes["win_rate"],
        "win_rate_change": (current_outcomes["win_rate"] - prior_outcomes["win_rate"]) if current_outcomes["win_rate"] is not None and prior_outcomes["win_rate"] is not None else None,
        "profit_factor": outcomes["profit_factor"],
        "profit_factor_change": (float(current_outcomes["profit_factor"]) - float(prior_outcomes["profit_factor"])) if current_outcomes["profit_factor"] is not None and prior_outcomes["profit_factor"] is not None else None,
        "trend": {"daily_counts": trend_counts, "daily_active_counts": trend_active, "daily_win_rates": daily_win_rates, "daily_profit_factors": daily_profit_factors},
        "last_updated": latest.isoformat() if latest else None,
        "service_state": "available" if category_counts["all"] else "empty",
    }
    performance = outcomes
    try:
        assets = list(MarketSymbol.objects.filter(is_active=True, is_tradable=True, symbol__in=base.values("symbol")).values_list("symbol", flat=True).distinct().order_by("symbol")[:500])
        markets = list(MarketSymbol.objects.filter(is_active=True, is_tradable=True, symbol__in=base.values("symbol")).values_list("market", flat=True).distinct().order_by("market"))
    except Exception:
        log.exception("Unable to load Signals filter catalog")
        assets, markets = list(base.values_list("symbol", flat=True).distinct()[:500]), []
    recent_rows = list(base.select_related("strategy", "configuration").order_by("-timestamp", "-pk")[:5])
    recent_lookup = {m.symbol: m for m in MarketSymbol.objects.filter(symbol__in=[r.symbol for r in recent_rows]).only("symbol", "display_name", "market")}
    return JsonResponse({
        "status": "success", "signals": [_serialize(r, market_lookup) for r in page_rows],
        "count": total, "total_unfiltered": category_counts["all"], "page": page, "page_size": page_size, "pages": pages,
        "start": start + 1 if total else 0, "end": min(start + len(page_rows), total),
        "category_counts": category_counts, "metrics": metrics, "performance": performance,
        "recent": [_serialize(r, recent_lookup) for r in recent],
        "assets": assets, "markets": [m for m in markets if m],
        "sentiment": {"status": "unavailable", "reason": "No authoritative account-scoped market-sentiment source is currently wired to this workspace."},
        "account": {"broker": account.broker.name, "account_id": account.account_id, "environment": account.account_type, "currency": account.currency},
        "generated_at": now.isoformat(),
    })
