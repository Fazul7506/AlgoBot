from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from apps.strategies.models import StrategySignal


@login_required
def strategy_signals(request):
    """Authenticated canonical strategy-signal feed for the current user.

    Analysis remains untouched. Signals exposes persisted signal records only,
    while preserving the evidence/diagnostic fields produced by the strategy
    pipeline in ``metadata``.
    """
    try:
        limit = min(max(int(request.GET.get("limit", 50)), 1), 100)
    except (TypeError, ValueError):
        limit = 50

    queryset = (
        StrategySignal.objects
        .select_related("strategy", "configuration")
        .filter(configuration__user=request.user)
        .order_by("-timestamp")
    )

    rows = []
    for signal in queryset[:limit]:
        metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
        rows.append({
            "id": signal.id,
            "symbol": signal.symbol,
            "display_name": metadata.get("display_name") or metadata.get("instrument") or signal.symbol,
            "direction": signal.signal,
            "signal_type": signal.signal,
            "confidence": signal.confidence,
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

    return JsonResponse({
        "status": "success",
        "count": len(rows),
        "data": rows,
    })
