from rest_framework import viewsets, permissions, decorators, response
from .models import Backtest, BacktestStatistics
from .serializers import BacktestSerializer, BacktestStatisticsSerializer
from .services import BacktestingEngine, MarketEvent, PaperTradingEngine, ParameterOptimizationService, ReplayService
class BacktestViewSet(viewsets.ModelViewSet):
    serializer_class=BacktestSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return Backtest.objects.filter(user=self.request.user)
    def perform_create(self, serializer): serializer.save(user=self.request.user,status='pending')
class StatisticsViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=BacktestStatisticsSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return BacktestStatistics.objects.filter(backtest__user=self.request.user)
@decorators.api_view(['POST'])
def paper_start(request): return response.Response(PaperTradingEngine().start())
@decorators.api_view(['POST'])
def paper_stop(request): return response.Response(PaperTradingEngine().stop())
@decorators.api_view(['GET'])
def paper_account(request): return response.Response({'balance':100000,'equity':100000,'currency':'USD'})
@decorators.api_view(['POST'])
def optimization_start(request): return response.Response({'status':'started','results':ParameterOptimizationService().optimize(request.data.get('optimizer','grid'), request.data.get('space',{'x':[1]}))})
@decorators.api_view(['GET'])
def optimization_results(request): return response.Response({'results':[]})
@decorators.api_view(['GET'])
def replay(request): return response.Response(ReplayService().play())
