from rest_framework import generics, permissions, throttling
from rest_framework.response import Response

from apps.analysis.services import AnalysisService
from apps.market_data.research_data import ResearchDataService
from .models import Indicator, IndicatorValue
from .serializers import IndicatorSerializer, IndicatorValueSerializer


def market_candles(symbol, timeframe):
    return ResearchDataService().candles(symbol, timeframe, limit=120)


def analysis_response(request, analyzer):
    symbol = request.GET.get('symbol', 'R_100')
    timeframe = request.GET.get('timeframe', '1m')
    try:
        candles = market_candles(symbol, timeframe)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=404)
    if not candles:
        return Response({'detail': 'No persisted market candles are available for this symbol/timeframe.'}, status=503)
    return Response(analyzer(symbol, timeframe, candles))


class AnalysisThrottle(throttling.UserRateThrottle):
    rate = '120/min'


class IndicatorListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AnalysisThrottle]
    serializer_class = IndicatorSerializer
    queryset = Indicator.objects.all()


class SymbolIndicatorAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AnalysisThrottle]
    serializer_class = IndicatorValueSerializer

    def get_queryset(self):
        return IndicatorValue.objects.filter(symbol=self.kwargs['symbol']).order_by('-timestamp')


class TrendAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AnalysisThrottle]

    def get(self, request):
        return analysis_response(request, AnalysisService().trend.analyze)


class PatternAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AnalysisThrottle]

    def get(self, request):
        return analysis_response(request, AnalysisService().patterns.detect)


class SupportResistanceAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AnalysisThrottle]

    def get(self, request):
        return analysis_response(request, AnalysisService().support_resistance.detect)


class VolatilityAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AnalysisThrottle]

    def get(self, request):
        return analysis_response(request, AnalysisService().volatility.analyze)
