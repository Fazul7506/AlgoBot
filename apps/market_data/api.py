import asyncio
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import MarketSymbol, Tick, Candle, MarketSnapshot, MarketStatistics
from .serializers import MarketSymbolSerializer, TickSerializer, CandleSerializer, MarketSnapshotSerializer, MarketStatisticsSerializer
from .deriv_sync import fetch_tick, sync_active_symbols
from .services import MarketDataService
from apps.brokers.models import BrokerAccount
from apps.brokers.services import BrokerRegistry
from apps.brokers.exceptions import BrokerConnectionError, BrokerAuthenticationError, BrokerOrderError


def _limit(request, default=500, maximum=1000):
    try: return max(1, min(int(request.query_params.get("limit", default)), maximum))
    except (TypeError, ValueError): return default


def _connected_account(user):
    return BrokerAccount.objects.filter(user=user, status="active", broker__status="active").select_related("broker").order_by("-is_preferred", "-id").first()


def _last_known_tick(symbol):
    return Tick.objects.select_related("symbol").filter(symbol__symbol=symbol).order_by("-epoch", "-received_at").first()


def _stale_tick_response(tick, account):
    payload = TickSerializer(tick).data
    payload.update({"broker": account.broker.name, "account_id": account.account_id, "stale": True, "source": "last_known_broker_quote"})
    return Response(payload, status=status.HTTP_200_OK)


async def _bounded_market_data(adapter, symbol, timeout=7.0):
    return await asyncio.wait_for(adapter.get_market_data(symbol), timeout=timeout)


@api_view(["GET"])
@permission_classes([AllowAny])
def markets(request): return Response({"markets": sorted(set(MarketSymbol.objects.values_list("market", flat=True)))})

@api_view(["GET"])
@permission_classes([AllowAny])
def symbols(request): return Response(MarketSymbolSerializer(MarketSymbol.objects.filter(is_active=True), many=True).data)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def broker_catalogue(request):
    """Return the authenticated broker catalogue from the local market registry."""
    try:
        queryset = MarketSymbol.objects.filter(is_active=True, is_tradable=True).order_by("market", "symbol")
        data = MarketSymbolSerializer(queryset, many=True).data
        return Response({"status": "ok", "source": "backend_market_catalogue", "symbols": data, "count": len(data)})
    except Exception as exc:
        return Response({"status": "error", "code": "MARKET_CATALOGUE_READ_FAILED", "detail": "Market catalogue could not be read.", "error_type": exc.__class__.__name__}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

@api_view(["GET"])
@permission_classes([AllowAny])
def symbol_detail(request, symbol): return Response(MarketSymbolSerializer(get_object_or_404(MarketSymbol, symbol=symbol, is_active=True)).data)

@api_view(["GET"])
@permission_classes([AllowAny])
def latest_tick(request):
    qs = Tick.objects.select_related("symbol")
    if request.query_params.get("symbol"): qs = qs.filter(symbol__symbol=request.query_params["symbol"])
    tick = qs.order_by("-epoch").first(); return Response(TickSerializer(tick).data if tick else {})

@api_view(["GET"])
@permission_classes([AllowAny])
def tick_history(request):
    qs = Tick.objects.select_related("symbol").order_by("-epoch")
    if request.query_params.get("symbol"): qs = qs.filter(symbol__symbol=request.query_params["symbol"])
    return Response(TickSerializer(qs[:_limit(request)], many=True).data)

@api_view(["GET"])
@permission_classes([AllowAny])
def candles(request): return Response(CandleSerializer(Candle.objects.select_related("symbol").order_by("-epoch")[:_limit(request)], many=True).data)

@api_view(["GET"])
@permission_classes([AllowAny])
def candle_history(request):
    qs = Candle.objects.select_related("symbol").order_by("-epoch")
    if request.query_params.get("symbol"): qs = qs.filter(symbol__symbol=request.query_params["symbol"])
    if request.query_params.get("timeframe"): qs = qs.filter(timeframe=request.query_params["timeframe"])
    return Response(CandleSerializer(qs[:_limit(request)], many=True).data)

@api_view(["GET"])
@permission_classes([AllowAny])
def statistics(request): return Response(MarketStatisticsSerializer(MarketStatistics.objects.all()[:100], many=True).data)

@api_view(["GET"])
@permission_classes([AllowAny])
def snapshot(request):
    qs = MarketSnapshot.objects.select_related("symbol")
    if request.query_params.get("symbol"): qs = qs.filter(symbol__symbol=request.query_params["symbol"])
    return Response(MarketSnapshotSerializer(qs, many=True).data)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_symbols(request):
    account = _connected_account(request.user)
    if not account: return Response({"status":"error","code":"NO_CONNECTED_BROKER","detail":"Connect a broker before synchronizing its market universe."}, status=status.HTTP_409_CONFLICT)
    if account.broker.broker_type != "deriv": return Response({"status":"error","code":"BROKER_MARKET_SYNC_UNSUPPORTED","detail":f"Market synchronization is not implemented for {account.broker.name} yet."}, status=status.HTTP_409_CONFLICT)
    try:
        count = sync_active_symbols(); return Response({"status":"ok","symbols":count,"broker":account.broker.name,"account_id":account.account_id,"source":"deriv_active_symbols","stale":False})
    except Exception:
        cached_count = MarketSymbol.objects.filter(broker="deriv", is_active=True).count()
        if cached_count: return Response({"status":"stale","symbols":cached_count,"broker":account.broker.name,"account_id":account.account_id,"source":"cached_deriv_active_symbols","stale":True,"detail":"Live broker market catalogue refresh is temporarily unavailable; serving the last known broker catalogue."})
        return Response({"status":"error","code":"BROKER_MARKET_SYNC_FAILED","detail":"Live broker market catalogue is temporarily unavailable and no cached catalogue exists."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def broker_tick(request):
    symbol = str((request.data.get("symbol") if request.method == "POST" else request.query_params.get("symbol")) or "").strip()
    if not symbol: return Response({"detail":"symbol is required"}, status=status.HTTP_400_BAD_REQUEST)
    account = _connected_account(request.user)
    if not account: return Response({"detail":"Connect a broker before requesting live broker quotes."}, status=status.HTTP_409_CONFLICT)
    if not MarketSymbol.objects.filter(symbol=symbol, is_active=True).exists(): return Response({"detail":"The requested symbol is not in the current broker market catalogue."}, status=status.HTTP_404_NOT_FOUND)
    try:
        if account.broker.broker_type == "deriv": data = fetch_tick(symbol)
        else: data = asyncio.run(_bounded_market_data(BrokerRegistry().adapter(account.broker, account), symbol))
        tick = MarketDataService().tick_service.ingest({"symbol": symbol, "quote": data.get("price", data.get("quote")), "bid": data.get("bid"), "ask": data.get("ask"), "epoch": data.get("epoch"), "volume": data.get("volume", 0)})
        payload = TickSerializer(tick).data; payload.update({"broker":account.broker.name,"account_id":account.account_id,"stale":False,"source":"live_broker_quote"}); return Response(payload)
    except BrokerAuthenticationError as exc:
        cached = _last_known_tick(symbol); return _stale_tick_response(cached, account) if cached else Response({"status":"error","code":"BROKER_AUTHENTICATION_FAILED","detail":str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
    except (BrokerConnectionError, BrokerOrderError, RuntimeError, asyncio.TimeoutError) as exc:
        cached = _last_known_tick(symbol); return _stale_tick_response(cached, account) if cached else Response({"status":"error","code":"BROKER_TICK_FAILED","detail":str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except Exception:
        cached = _last_known_tick(symbol); return _stale_tick_response(cached, account) if cached else Response({"status":"error","code":"BROKER_TICK_FAILED","detail":"Broker market data request failed."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def broker_chart_capabilities(request):
    account = _connected_account(request.user)
    if not account: return Response({"detail":"Connect a broker before loading chart capabilities."}, status=status.HTTP_409_CONFLICT)
    try:
        adapter = BrokerRegistry().adapter(account.broker, account)
        if not hasattr(adapter, "get_chart_capabilities"):
            return Response({"broker": account.broker.name, "modes": ["ticks", "candles"], "timeframes": ["M1", "M5", "M15", "M30", "H1", "H4", "D1"], "source": "backend_default"})
        return Response(awaitable_to_sync(adapter.get_chart_capabilities()))
    except Exception:
        return Response({"broker": account.broker.name, "modes": ["ticks", "candles"], "timeframes": ["M1", "M5", "M15", "M30", "H1", "H4", "D1"], "source": "safe_backend_fallback", "stale": True}, status=status.HTTP_200_OK)


def awaitable_to_sync(awaitable): return asyncio.run(asyncio.wait_for(awaitable, timeout=7.0))

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def broker_chart_history(request):
    symbol = str(request.query_params.get("symbol") or "").strip()
    mode = str(request.query_params.get("mode") or "ticks").lower().strip()
    granularity = request.query_params.get("granularity")
    if not symbol: return Response({"detail":"symbol is required"}, status=status.HTTP_400_BAD_REQUEST)
    if mode not in {"ticks", "candles"}: return Response({"detail":"mode must be ticks or candles"}, status=status.HTTP_400_BAD_REQUEST)
    account = _connected_account(request.user)
    if not account: return Response({"detail":"Connect a broker before loading live chart history."}, status=status.HTTP_409_CONFLICT)
    try:
        adapter = BrokerRegistry().adapter(account.broker, account)
        if not hasattr(adapter, "get_chart_history"): return Response({"detail":"The connected broker does not expose chart history through its adapter."}, status=status.HTTP_409_CONFLICT)
        data = awaitable_to_sync(adapter.get_chart_history(symbol, mode=mode, count=_limit(request, 120, 1000), granularity=granularity))
        data.update({"broker": account.broker.name, "account_id": account.account_id, "source": "live_broker"})
        return Response(data)
    except (BrokerAuthenticationError, BrokerConnectionError, BrokerOrderError, asyncio.TimeoutError) as exc:
        return Response({"detail":str(exc),"source":"broker","stale":False}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
