from collections import Counter
from decimal import Decimal

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import MarketSymbol
from trading.models.core import Signal

SNAPSHOT_FRESHNESS_SECONDS = 30
SIGNAL_ACTIVE_SECONDS = 300


def _limit(request, default=50, maximum=100):
    try:
        return max(1, min(int(request.query_params.get("limit", default)), maximum))
    except (TypeError, ValueError):
        return default


def _fresh(snapshot, now):
    if snapshot is None:
        return False, None
    age = max(0, int((now - snapshot.timestamp).total_seconds()))
    return age <= SNAPSHOT_FRESHNESS_SECONDS, age


def _signal_confluence(signals):
    directions = Counter(s.direction for s in signals if s.direction in {"BUY", "SELL"})
    if not directions:
        return None, 0, 0, 0.0, []
    dominant, dominant_count = directions.most_common(1)[0]
    opposing = directions.get("SELL" if dominant == "BUY" else "BUY", 0)
    total = dominant_count + opposing
    agreement = dominant_count / total if total else 0.0
    confidences = [max(0.0, min(1.0, float(s.confidence or 0))) for s in signals if s.direction in {"BUY", "SELL"}]
    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    timeframes = sorted({str(s.timeframe).strip() for s in signals if str(s.timeframe).strip()})
    return dominant, dominant_count, opposing, agreement * confidence, timeframes


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def market_intelligence(request):
    """Return broker-backed market intelligence without fabricating observations."""
    symbol_filter = str(request.query_params.get("symbol") or "").strip()
    fresh_only = str(request.query_params.get("fresh_only") or "").lower() in {"1", "true", "yes"}
    now = timezone.now()
    symbols = MarketSymbol.objects.filter(is_active=True, is_tradable=True).select_related("snapshot")
    if symbol_filter:
        symbols = symbols.filter(symbol=symbol_filter)
    symbol_values = list(symbols.values_list("symbol", flat=True))
    signals = Signal.objects.filter(symbol__in=symbol_values).order_by("-created_at")
    signals_by_symbol = {}
    for signal in signals:
        signals_by_symbol.setdefault(signal.symbol, []).append(signal)
    results = []
    for market in symbols[:_limit(request)]:
        snapshot = getattr(market, "snapshot", None)
        is_fresh, freshness_seconds = _fresh(snapshot, now)
        if fresh_only and not is_fresh:
            continue
        recent = signals_by_symbol.get(market.symbol, [])[:12]
        dominant, buy_count, sell_count, signal_strength, timeframes = _signal_confluence(recent)
        evidence = []
        price_score = Decimal("0")
        if snapshot is not None:
            change = Decimal(str(snapshot.change_percent or 0))
            if change > 0:
                price_score += Decimal("1")
                evidence.append("positive_price_change")
            elif change < 0:
                price_score -= Decimal("1")
                evidence.append("negative_price_change")
            evidence.append("broker_spread_observed")
            evidence.append("fresh_broker_snapshot" if is_fresh else "stale_broker_snapshot")
        if dominant:
            evidence.append(f"signal_confluence_{dominant.lower()}")
        direction_score = Decimal(str(signal_strength))
        if dominant == "SELL":
            direction_score *= -1
        combined_score = price_score + direction_score
        results.append({
            "symbol": market.symbol,
            "display_name": market.display_name,
            "market": market.market,
            "sub_market": market.sub_market,
            "tradable": bool(market.is_tradable),
            "status": "ready" if is_fresh else ("stale" if snapshot is not None else "no_data"),
            "fresh": is_fresh,
            "freshness_seconds": freshness_seconds,
            "confluence_score": round(float(combined_score), 6),
            "signal_strength": round(float(signal_strength), 6),
            "dominant_direction": dominant,
            "signal_count": len(recent),
            "buy_signals": buy_count,
            "sell_signals": sell_count,
            "timeframes": timeframes,
            "evidence": evidence,
            "snapshot_timestamp": snapshot.timestamp.isoformat() if snapshot else None,
            "source": "broker_snapshot_store_and_strategy_signals",
        })
    results.sort(key=lambda row: row["confluence_score"], reverse=True)
    return Response({
        "status": "ok",
        "source": "backend_market_intelligence",
        "freshness_policy_seconds": SNAPSHOT_FRESHNESS_SECONDS,
        "count": len(results),
        "results": results,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def signal_lifecycle(request):
    """Expose deterministic signal lifecycle state from persisted strategy signals."""
    symbol = str(request.query_params.get("symbol") or "").strip()
    qs = Signal.objects.all().order_by("-created_at")
    if symbol:
        qs = qs.filter(symbol=symbol)
    now = timezone.now()
    data = []
    for signal in qs[:_limit(request, 100, 100)]:
        age_seconds = max(0, int((now - signal.created_at).total_seconds()))
        lifecycle = "executed" if signal.was_executed else ("active" if age_seconds <= SIGNAL_ACTIVE_SECONDS else "expired")
        data.append({
            "id": signal.id,
            "symbol": signal.symbol,
            "direction": signal.direction,
            "confidence": signal.confidence,
            "strategy": signal.strategy,
            "timeframe": signal.timeframe,
            "market_regime": signal.market_regime,
            "created_at": signal.created_at.isoformat(),
            "age_seconds": age_seconds,
            "lifecycle": lifecycle,
            "was_executed": signal.was_executed,
        })
    return Response({
        "status": "ok",
        "source": "persisted_strategy_signals",
        "active_window_seconds": SIGNAL_ACTIVE_SECONDS,
        "count": len(data),
        "signals": data,
    })
