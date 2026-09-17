from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from apps.strategies.models import StrategySignal


@login_required
def strategy_signals(request):
    """Return current persisted scan signals with the same market context used by Analysis."""
    try:
        limit = min(max(int(request.GET.get("limit", 100)), 1), 100)
    except (TypeError, ValueError):
        limit = 100

    queryset = (
        StrategySignal.objects
        .select_related("strategy", "configuration")
        .filter(Q(configuration__user=request.user) | Q(configuration__isnull=True))
        .order_by("-timestamp")
    )

    rows = []
    for signal in queryset[:limit]:
        metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
        rows.append({
            "id": signal.id,
            "symbol": signal.symbol,
            "display_name": metadata.get("display_name") or metadata.get("instrument") or signal.symbol,
            "instrument": metadata.get("instrument") or signal.symbol,
            "timeframe": metadata.get("timeframe") or metadata.get("interval") or getattr(signal.configuration, "timeframe", None) or "—",
            "direction": signal.signal,
            "signal_type": signal.signal,
            "confidence": signal.confidence,
            "score": metadata.get("score") or metadata.get("signal_score") or "—",
            "price": metadata.get("price") or metadata.get("current_price") or metadata.get("last_price") or "—",
            "market_regime": metadata.get("market_regime") or metadata.get("regime") or "—",
            "strategy": signal.strategy.name,
            "strategy_name": signal.strategy.name,
            "was_executed": bool(metadata.get("was_executed", False)),
            "created_at": signal.timestamp,
            "timestamp": signal.timestamp,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "entry_condition": metadata.get("entry_condition") or metadata.get("entry") or "—",
            "risk_gate": metadata.get("risk_gate") or metadata.get("risk_status") or "—",
            "trend_confirmation": metadata.get("trend_confirmation") or metadata.get("trend") or "—",
            "momentum_confirmation": metadata.get("momentum_confirmation") or metadata.get("momentum") or "—",
            "data_freshness": metadata.get("data_freshness") or metadata.get("data_status") or "—",
            "broker_availability": metadata.get("broker_availability") or metadata.get("execution_availability") or "—",
            "evidence": metadata.get("evidence") or metadata.get("reason") or metadata.get("explanation") or "—",
            "reason": metadata.get("reason") or metadata.get("explanation") or metadata.get("evidence") or "—",
            "confirmation": metadata.get("confirmation") or metadata.get("confirmation_reason") or "—",
            "confirmation_status": metadata.get("confirmation_status") or metadata.get("trigger_status") or "—",
            "status": metadata.get("status") or metadata.get("trigger_status") or "—",
            "metadata": metadata,
        })

    return JsonResponse({"status": "success", "count": len(rows), "data": rows})
