from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import MarketSymbol, Tick, Candle, MarketSnapshot, MarketStatistics
from .serializers import MarketSymbolSerializer, TickSerializer, CandleSerializer, MarketSnapshotSerializer, MarketStatisticsSerializer

def _limit(request, default=500, maximum=1000):
    try:
        return max(1, min(int(request.query_params.get("limit", default)), maximum))
    except (TypeError, ValueError):
        return default

@api_view(["GET"])
@permission_classes([AllowAny])
def markets(request):
    return Response({"markets": sorted(set(MarketSymbol.objects.values_list("market", flat=True)))})

@api_view(["GET"])
@permission_classes([AllowAny])
def symbols(request):
    return Response(MarketSymbolSerializer(MarketSymbol.objects.filter(is_active=True), many=True).data)

@api_view(["GET"])
@permission_classes([AllowAny])
def symbol_detail(request, symbol):
    return Response(MarketSymbolSerializer(get_object_or_404(MarketSymbol, symbol=symbol, is_active=True)).data)

@api_view(["GET"])
@permission_classes([AllowAny])
def latest_tick(request):
    symbol = request.query_params.get("symbol")
    qs = Tick.objects.select_related("symbol")
    if symbol: qs = qs.filter(symbol__symbol=symbol)
    tick = qs.order_by("-epoch").first()
    return Response(TickSerializer(tick).data if tick else {})

@api_view(["GET"])
@permission_classes([AllowAny])
def tick_history(request):
    qs = Tick.objects.select_related("symbol").order_by("-epoch")[:_limit(request)]
    if request.query_params.get("symbol"):
        qs = Tick.objects.select_related("symbol").filter(symbol__symbol=request.query_params["symbol"]).order_by("-epoch")[:_limit(request)]
    return Response(TickSerializer(qs, many=True).data)

@api_view(["GET"])
@permission_classes([AllowAny])
def candles(request):
    qs = Candle.objects.select_related("symbol").order_by("-epoch")[:_limit(request)]
    return Response(CandleSerializer(qs, many=True).data)

@api_view(["GET"])
@permission_classes([AllowAny])
def candle_history(request):
    qs = Candle.objects.select_related("symbol").order_by("-epoch")
    if request.query_params.get("symbol"): qs = qs.filter(symbol__symbol=request.query_params["symbol"])
    if request.query_params.get("timeframe"): qs = qs.filter(timeframe=request.query_params["timeframe"])
    return Response(CandleSerializer(qs[:_limit(request)], many=True).data)

@api_view(["GET"])
@permission_classes([AllowAny])
def statistics(request):
    return Response(MarketStatisticsSerializer(MarketStatistics.objects.all()[:100], many=True).data)

@api_view(["GET"])
@permission_classes([AllowAny])
def snapshot(request):
    qs = MarketSnapshot.objects.select_related("symbol")
    if request.query_params.get("symbol"): qs = qs.filter(symbol__symbol=request.query_params["symbol"])
    return Response(MarketSnapshotSerializer(qs, many=True).data)
