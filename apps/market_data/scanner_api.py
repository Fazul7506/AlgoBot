from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from core.account_context import get_active_account
from apps.indicators.calculator import IndicatorCalculator
from .historical import normalize_timeframe
from .models import Candle, MarketSymbol


DEFAULT_TIMEFRAME = "1m"
MAX_CANDLES_PER_SYMBOL = 200
SNAPSHOT_FRESHNESS_SECONDS = int(
    getattr(settings, "BROKER_MARKET_DATA_MAX_AGE_SECONDS", 30)
)


def _decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _bounded_limit(request):
    try:
        return max(1, min(int(request.query_params.get("limit", 100)), 250))
    except (TypeError, ValueError):
        return 100


def _technical_context(candles):
    if not candles:
        return {
            "technical_status": "no_data",
            "rsi": None,
            "sma_20": None,
            "sma_50": None,
            "ema_21": None,
            "macd": None,
            "macd_signal": None,
            "macd_histogram": None,
            "atr_14": None,
            "bollinger_width": None,
            "trend": None,
            "candles_used": 0,
        }

    calculator = IndicatorCalculator()
    payload = [
        {
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "epoch": c.epoch,
        }
        for c in reversed(candles)
    ]
    rsi = calculator.rsi(payload, 14)
    sma20 = calculator.sma(payload, 20)
    sma50 = calculator.sma(payload, 50)
    ema21 = calculator.ema(payload, 21)
    macd = calculator.macd(payload, 12, 26, 9)
    atr = calculator.atr(payload, 14)
    bands = calculator.bollinger_bands(payload, 20, 2)
    close = float(payload[-1]["close"])
    trend = None
    if sma20 is not None and sma50 is not None:
        if close > sma20 > sma50:
            trend = "bullish"
        elif close < sma20 < sma50:
            trend = "bearish"
        else:
            trend = "neutral"

    width = None
    if bands and bands["middle"]:
        width = ((bands["upper"] - bands["lower"]) / bands["middle"]) * 100

    available = sum(
        value is not None
        for value in (rsi, sma20, sma50, ema21, macd.get("macd"), atr)
    )
    technical_status = "ready" if available >= 4 else "insufficient_data"
    return {
        "technical_status": technical_status,
        "rsi": rsi,
        "sma_20": sma20,
        "sma_50": sma50,
        "ema_21": ema21,
        "macd": macd.get("macd"),
        "macd_signal": macd.get("signal"),
        "macd_histogram": macd.get("histogram"),
        "atr_14": atr,
        "bollinger_width": width,
        "trend": trend,
        "candles_used": len(payload),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def scanner(request):
    """Scan the selected user's broker universe using persisted broker data only."""
    account = get_active_account(request.user, request=request)
    if not account:
        return Response(
            {
                "status": "error",
                "code": "NO_CONNECTED_BROKER",
                "detail": "Connect a broker before running the market scanner.",
            },
            status=status.HTTP_409_CONFLICT,
        )

    try:
        timeframe = normalize_timeframe(
            str(request.query_params.get("timeframe") or DEFAULT_TIMEFRAME)
        )
    except Exception:
        return Response(
            {
                "status": "error",
                "code": "INVALID_TIMEFRAME",
                "detail": "Unsupported scanner timeframe.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    market = str(request.query_params.get("market") or "").strip()
    search = str(request.query_params.get("search") or "").strip()
    direction = str(request.query_params.get("direction") or "all").lower().strip()
    sort = str(request.query_params.get("sort") or "change_percent").lower().strip()
    trend = str(request.query_params.get("trend") or "all").lower().strip()
    min_change = _decimal(request.query_params.get("min_change"))
    max_change = _decimal(request.query_params.get("max_change"))
    max_spread = _decimal(request.query_params.get("max_spread"))
    min_rsi = _decimal(request.query_params.get("min_rsi"))
    max_rsi = _decimal(request.query_params.get("max_rsi"))

    if direction not in {"all", "gainers", "losers"}:
        return Response(
            {"status": "error", "code": "INVALID_DIRECTION", "detail": "direction must be all, gainers, or losers."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if sort not in {"change_percent", "price", "spread", "volume", "symbol", "rsi"}:
        return Response(
            {"status": "error", "code": "INVALID_SORT", "detail": "sort must be change_percent, price, spread, volume, symbol, or rsi."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if trend not in {"all", "bullish", "bearish", "neutral"}:
        return Response(
            {"status": "error", "code": "INVALID_TREND", "detail": "trend must be all, bullish, bearish, or neutral."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    queryset = (
        MarketSymbol.objects.filter(
            broker=account.broker.broker_type,
            is_active=True,
            is_tradable=True,
        )
        .select_related("snapshot")
        .order_by("market", "symbol")
    )
    if market:
        queryset = queryset.filter(market=market)
    if search:
        queryset = queryset.filter(
            Q(symbol__icontains=search) | Q(display_name__icontains=search)
        )

    symbols = list(queryset)
    symbol_ids = [row.id for row in symbols]
    candle_rows = list(
        Candle.objects.filter(symbol_id__in=symbol_ids, timeframe=timeframe)
        .order_by("symbol_id", "-epoch")[: max(1, len(symbol_ids) * MAX_CANDLES_PER_SYMBOL)]
    )
    candles_by_symbol = {}
    for candle in candle_rows:
        bucket = candles_by_symbol.setdefault(candle.symbol_id, [])
        if len(bucket) < MAX_CANDLES_PER_SYMBOL:
            bucket.append(candle)

    now = timezone.now()
    rows = []
    for symbol in symbols:
        snapshot = getattr(symbol, "snapshot", None)
        if snapshot is None:
            if direction != "all" or min_change is not None or max_change is not None or max_spread is not None:
                continue
            rows.append(
                {
                    "symbol": symbol.symbol,
                    "display_name": symbol.display_name,
                    "market": symbol.market,
                    "sub_market": symbol.sub_market,
                    "currency": symbol.currency,
                    "status": "no_data",
                    "source": "broker_snapshot_store",
                    "technical_source": "persisted_broker_candles",
                    "fresh": False,
                    "freshness_seconds": None,
                    "timeframe": timeframe,
                    **_technical_context(candles_by_symbol.get(symbol.id, [])),
                }
            )
            continue

        age = max(0, int((now - snapshot.timestamp).total_seconds()))
        fresh = age <= SNAPSHOT_FRESHNESS_SECONDS
        change = Decimal(snapshot.change_percent or 0)
        spread = Decimal(snapshot.spread or 0)
        volume = Decimal(snapshot.volume or 0)
        technical = _technical_context(candles_by_symbol.get(symbol.id, []))
        rsi = _decimal(technical["rsi"])
        row_trend = technical["trend"]

        # Stale observations remain visible so users can diagnose the feed,
        # but they cannot pass directional/numeric/technical opportunity filters.
        requires_current_data = (
            direction != "all"
            or min_change is not None
            or max_change is not None
            or max_spread is not None
            or min_rsi is not None
            or max_rsi is not None
            or trend != "all"
        )
        if requires_current_data and not fresh:
            continue
        if min_change is not None and change < min_change:
            continue
        if max_change is not None and change > max_change:
            continue
        if max_spread is not None and spread > max_spread:
            continue
        if direction == "gainers" and change <= 0:
            continue
        if direction == "losers" and change >= 0:
            continue
        if min_rsi is not None and (rsi is None or rsi < min_rsi):
            continue
        if max_rsi is not None and (rsi is None or rsi > max_rsi):
            continue
        if trend != "all" and row_trend != trend:
            continue

        rows.append(
            {
                "symbol": symbol.symbol,
                "display_name": symbol.display_name,
                "market": symbol.market,
                "sub_market": symbol.sub_market,
                "currency": symbol.currency,
                "status": "ready" if fresh else "stale",
                "source": "broker_snapshot_store",
                "technical_source": "persisted_broker_candles",
                "fresh": fresh,
                "freshness_seconds": age,
                "timeframe": timeframe,
                "last_price": str(snapshot.last_price),
                "bid": str(snapshot.bid) if snapshot.bid is not None else None,
                "ask": str(snapshot.ask) if snapshot.ask is not None else None,
                "spread": str(spread),
                "high": str(snapshot.high),
                "low": str(snapshot.low),
                "change": str(snapshot.change),
                "change_percent": str(change),
                "volume": str(volume),
                "timestamp": snapshot.timestamp.isoformat(),
                **technical,
            }
        )

    def sort_key(row):
        if sort == "symbol":
            return row["symbol"].lower()
        if row["status"] != "ready":
            return Decimal("-Infinity")
        field = {
            "change_percent": "change_percent",
            "price": "last_price",
            "spread": "spread",
            "volume": "volume",
            "rsi": "rsi",
        }[sort]
        value = _decimal(row.get(field))
        return value if value is not None else Decimal("-Infinity")

    rows.sort(key=sort_key, reverse=sort != "symbol")
    limit = _bounded_limit(request)
    return Response(
        {
            "status": "ok",
            "source": "broker_snapshot_store",
            "technical_source": "persisted_broker_candles",
            "broker": account.broker.name,
            "account_id": account.account_id,
            "timeframe": timeframe,
            "freshness_threshold_seconds": SNAPSHOT_FRESHNESS_SECONDS,
            "count": min(len(rows), limit),
            "total_available": len(rows),
            "results": rows[:limit],
        }
    )
