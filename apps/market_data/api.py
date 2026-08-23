import asyncio
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import MarketSymbol, Tick, Candle, MarketSnapshot, MarketStatistics
from .serializers import MarketSymbolSerializer, TickSerializer, CandleSerializer, MarketSnapshotSerializer, MarketStatisticsSerializer
from .deriv_sync import sync_active_symbols
from .services import MarketDataService
from apps.brokers.models import BrokerAccount
from apps.brokers.services import BrokerRegistry
from apps.brokers.exceptions import BrokerConnectionError, BrokerAuthenticationError, BrokerOrderError


def _limit(request, default=500, maximum=1000):
    try: return max(1, min(int(request.query_params.get("limit", default)), maximum))
    except (TypeError, ValueError): return default


def _connected_account(user):
    return BrokerAccount.objects.filter(user=user, status="active", broker__status="active").select_related("broker").order_by("-is_preferred", "-id").first()


@api_view(["GET"])
@permission_classes([AllowAny])
def markets(request): return Response({"markets": sorted(set(MarketSymbol.objects.values_list("market", flat=True)))})

@api_view(["GET"])
@permission_classes([AllowAny])
def symbols(request): return Response(MarketSymbolSerializer(MarketSymbol.objects.filter(is_active=True), many=True).data)

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
    try: return Response({"status":"ok","symbols":sync_active_symbols(),"broker":account.broker.name,"account_id":account.account_id,"source":"deriv_active_symbols"})
    except Exception as exc: return Response({"status":"error","code":"BROKER_MARKET_SYNC_FAILED","detail":str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def broker_tick(request):
    """Fetch a live quote through the selected broker adapter and persist it."""
    symbol = str((request.data.get("symbol") if request.method == "POST" else request.query_params.get("symbol")) or "").strip()
    if not symbol: return Response({"detail":"symbol is required"}, status=status.HTTP_400_BAD_REQUEST)
    account = _connected_account(request.user)
    if not account: return Response({"detail":"Connect a broker before requesting live broker quotes."}, status=status.HTTP_409_CONFLICT)
    if not MarketSymbol.objects.filter(symbol=symbol, is_active=True).exists(): return Response({"detail":"The requested symbol is not in the current broker market catalogue."}, status=status.HTTP_404_NOT_FOUND)
    try:
        data = asyncio.run(BrokerRegistry().adapter(account.broker, account).get_market_data(symbol))
        tick = MarketDataService().tick_service.ingest({"symbol": symbol, "quote": data.get("price"), "bid": data.get("bid"), "ask": data.get("ask"), "epoch": data.get("epoch"), "volume": data.get("volume", 0)})
        payload = TickSerializer(tick).data
        payload.update({"broker":account.broker.name,"account_id":account.account_id})
        return Response(payload)
    except BrokerAuthenticationError as exc: return Response({"status":"error","code":"BROKER_AUTHENTICATION_FAILED","detail":str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
    except (BrokerConnectionError, BrokerOrderError) as exc: return Response({"status":"error","code":"BROKER_TICK_FAILED","detail":str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except Exception as exc: return Response({"status":"error","code":"BROKER_TICK_FAILED","detail":"Broker market data request failed."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
