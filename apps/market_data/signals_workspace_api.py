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
        "average_profit": str(gross_profit / wins) if wins and gross_profit else None,
        "average_loss": str(gross_loss / losses) if losses and gross_loss else None,
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

    # Aggregate in SQL where possible; the account scope is applied before any data is read.
    recent_start = now - timedelta(days=7)
    prior_start = now - timedelta(days=14)
    all_rows = list(base.order_by("-timestamp", "-pk"))
    filtered = [row for row in all_rows if _matches_category(row, category)]
    total = len(filtered)
    pages = (total + page_size - 1) // page_size
    if pages and page > pages:
        page = pages
    start = (page - 1) * page_size
    page_rows = filtered[start:start + page_size]
    market_lookup = {m.symbol: m for m in MarketSymbol.objects.filter(symbol__in=[r.symbol for r in page_rows]).only("symbol", "display_name", "market")}

    category_counts = {"all": len(all_rows), "high_confidence": sum(1 for row in all_rows if _matches_category(row, "high_confidence")),
                       "scalping": sum(1 for row in all_rows if _matches_category(row, "scalping")),
                       "intraday": sum(1 for row in all_rows if _matches_category(row, "intraday")),
                       "swing": sum(1 for row in all_rows if _matches_category(row, "swing"))}
    last_week = [r for r in all_rows if r.timestamp >= recent_start]
    prior_week = [r for r in all_rows if prior_start <= r.timestamp < recent_start]
    active_states = {"active", "actionable", "open", "live", "confirmed"}
    active_count = sum(1 for row in all_rows if _lifecycle(row) in active_states)
    metrics = {
        "total_signals": len(all_rows),
        "total_signals_change": len(last_week) - len(prior_week),
        "active_signals": active_count,
        "active_signals_change": sum(1 for r in last_week if _lifecycle(r) in active_states) - sum(1 for r in prior_week if _lifecycle(r) in active_states),
        "high_confidence_threshold": str(HIGH_CONFIDENCE_THRESHOLD),
        "win_rate": None, "win_rate_change": None, "profit_factor": None, "profit_factor_change": None,
        "trend": {"daily_counts": [sum(1 for r in all_rows if (now.date() - r.timestamp.date()).days == day) for day in range(6, -1, -1)], "daily_active_counts": [sum(1 for r in all_rows if (now.date() - r.timestamp.date()).days == day and _lifecycle(r) in {"active", "actionable", "open", "live", "confirmed"}) for day in range(6, -1, -1)], "daily_win_rates": [_outcome_stats([r for r in all_rows if (now.date() - r.timestamp.date()).days == day])["win_rate"] for day in range(6, -1, -1)], "daily_profit_factors": [_outcome_stats([r for r in all_rows if (now.date() - r.timestamp.date()).days == day])["profit_factor"] for day in range(6, -1, -1)]},
        "last_updated": max((r.timestamp for r in all_rows), default=None).isoformat() if all_rows else None,
        "service_state": "available" if all_rows else "empty",
    }
    outcomes = _outcome_stats(all_rows)
    metrics["win_rate"] = outcomes["win_rate"]
    metrics["profit_factor"] = outcomes["profit_factor"]
    current_outcomes = _outcome_stats([r for r in all_rows if r.timestamp >= recent_start])
    prior_outcomes = _outcome_stats([r for r in all_rows if prior_start <= r.timestamp < recent_start])
    metrics["win_rate_change"] = (current_outcomes["win_rate"] - prior_outcomes["win_rate"]) if current_outcomes["win_rate"] is not None and prior_outcomes["win_rate"] is not None else None
    metrics["profit_factor_change"] = (float(current_outcomes["profit_factor"]) - float(prior_outcomes["profit_factor"])) if current_outcomes["profit_factor"] is not None and prior_outcomes["profit_factor"] is not None else None
    performance = outcomes
    try:
        assets = list(MarketSymbol.objects.filter(is_active=True, is_tradable=True, symbol__in=base.values("symbol")).values_list("symbol", flat=True).distinct().order_by("symbol")[:500])
        markets = list(MarketSymbol.objects.filter(is_active=True, is_tradable=True, symbol__in=base.values("symbol")).values_list("market", flat=True).distinct().order_by("market"))
    except Exception:
        log.exception("Unable to load Signals filter catalog")
        assets, markets = sorted({r.symbol for r in all_rows}), sorted({str(_metadata(r).get("market_type") or "Unclassified") for r in all_rows})
    recent = list(base.select_related("strategy").order_by("-timestamp", "-pk")[:5])
    recent_lookup = {m.symbol: m for m in MarketSymbol.objects.filter(symbol__in=[r.symbol for r in recent]).only("symbol", "display_name", "market")}
    return JsonResponse({
        "status": "success", "signals": [_serialize(r, market_lookup) for r in page_rows],
        "count": total, "total_unfiltered": len(all_rows), "page": page, "page_size": page_size, "pages": pages,
        "start": start + 1 if total else 0, "end": min(start + len(page_rows), total),
        "category_counts": category_counts, "metrics": metrics, "performance": performance,
        "recent": [_serialize(r, recent_lookup) for r in recent],
        "assets": assets, "markets": [m for m in markets if m],
        "sentiment": {"status": "unavailable", "reason": "No authoritative account-scoped market-sentiment source is currently wired to this workspace."},
        "account": {"broker": account.broker.name, "account_id": account.account_id, "environment": account.account_type, "currency": account.currency},
        "generated_at": now.isoformat(),
    })
