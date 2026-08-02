from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import MarketSymbol, Tick, Candle, MarketSnapshot, MarketStatistics
from .serializers import MarketSymbolSerializer, TickSerializer, CandleSerializer, MarketSnapshotSerializer, MarketStatisticsSerializer

@api_view(["GET"])
@permission_classes([AllowAny])
def markets(request):
    return Response({"markets": sorted(set(MarketSymbol.objects.values_list("market", flat=True)))})

@api_view(["GET"])
@permission_classes([AllowAny])
def symbols(request):
    return Response(MarketSymbolSerializer(MarketSymbol.objects.all(), many=True).data)

@api_view(["GET"])
@permission_classes([AllowAny])
def symbol_detail(request, symbol):
    return Response(MarketSymbolSerializer(MarketSymbol.objects.get(symbol=symbol)).data)

@api_view(["GET"])
@permission_classes([AllowAny])
def latest_tick(request):
    symbol = request.query_params.get("symbol")
    qs = Tick.objects.all()
    if symbol: qs = qs.filter(symbol__symbol=symbol)
    return Response(TickSerializer(qs.order_by("-epoch").first()).data if qs.exists() else {})

@api_view(["GET"])
@permission_classes([AllowAny])
def tick_history(request):
    qs = Tick.objects.all().order_by("-epoch")[: int(request.query_params.get("limit", 500))]
    if request.query_params.get("symbol"):
        qs = Tick.objects.filter(symbol__symbol=request.query_params["symbol"]).order_by("-epoch")[: int(request.query_params.get("limit", 500))]
    return Response(TickSerializer(qs, many=True).data)

@api_view(["GET"])
@permission_classes([AllowAny])
def candles(request):
    qs = Candle.objects.all().order_by("-epoch")[: int(request.query_params.get("limit", 500))]
    return Response(CandleSerializer(qs, many=True).data)

@api_view(["GET"])
@permission_classes([AllowAny])
def candle_history(request):
    qs = Candle.objects.all().order_by("-epoch")
    if request.query_params.get("symbol"): qs = qs.filter(symbol__symbol=request.query_params["symbol"])
    if request.query_params.get("timeframe"): qs = qs.filter(timeframe=request.query_params["timeframe"])
    return Response(CandleSerializer(qs[: int(request.query_params.get("limit", 500))], many=True).data)

@api_view(["GET"])
@permission_classes([AllowAny])
def statistics(request):
    return Response(MarketStatisticsSerializer(MarketStatistics.objects.all()[:100], many=True).data)

@api_view(["GET"])
@permission_classes([AllowAny])
def snapshot(request):
    qs = MarketSnapshot.objects.all()
    if request.query_params.get("symbol"): qs = qs.filter(symbol__symbol=request.query_params["symbol"])
    return Response(MarketSnapshotSerializer(qs, many=True).data)
