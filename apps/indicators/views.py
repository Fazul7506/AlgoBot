from rest_framework import generics, permissions, throttling
from rest_framework.response import Response
from apps.analysis.services import AnalysisService
from .models import Indicator, IndicatorValue
from .serializers import IndicatorSerializer, IndicatorValueSerializer
from .services import IndicatorService

def sample_candles(): return [{'open':i,'high':i+1,'low':i-1,'close':i+0.5,'volume':100+i} for i in range(1,80)]
class AnalysisThrottle(throttling.UserRateThrottle): rate='120/min'
class IndicatorListAPIView(generics.ListAPIView):
    permission_classes=[permissions.IsAuthenticatedOrReadOnly]; throttle_classes=[AnalysisThrottle]; serializer_class=IndicatorSerializer; queryset=Indicator.objects.all()
class SymbolIndicatorAPIView(generics.ListAPIView):
    permission_classes=[permissions.IsAuthenticatedOrReadOnly]; throttle_classes=[AnalysisThrottle]; serializer_class=IndicatorValueSerializer
    def get_queryset(self): return IndicatorValue.objects.filter(symbol=self.kwargs['symbol']).order_by('-timestamp')
class TrendAPIView(generics.GenericAPIView):
    permission_classes=[permissions.IsAuthenticatedOrReadOnly]; throttle_classes=[AnalysisThrottle]
    def get(self,request): return Response(AnalysisService().trend.analyze(request.GET.get('symbol','R_100'), request.GET.get('timeframe','1m'), sample_candles()))
class PatternAPIView(generics.GenericAPIView):
    permission_classes=[permissions.IsAuthenticatedOrReadOnly]; throttle_classes=[AnalysisThrottle]
    def get(self,request): return Response(AnalysisService().patterns.detect(request.GET.get('symbol','R_100'), request.GET.get('timeframe','1m'), sample_candles()))
class SupportResistanceAPIView(generics.GenericAPIView):
    permission_classes=[permissions.IsAuthenticatedOrReadOnly]; throttle_classes=[AnalysisThrottle]
    def get(self,request): return Response(AnalysisService().support_resistance.detect(request.GET.get('symbol','R_100'), request.GET.get('timeframe','1m'), sample_candles()))
class VolatilityAPIView(generics.GenericAPIView):
    permission_classes=[permissions.IsAuthenticatedOrReadOnly]; throttle_classes=[AnalysisThrottle]
    def get(self,request): return Response(AnalysisService().volatility.analyze(request.GET.get('symbol','R_100'), request.GET.get('timeframe','1m'), sample_candles()))
