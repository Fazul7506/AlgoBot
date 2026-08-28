from django.utils.dateparse import parse_datetime
from rest_framework import viewsets, permissions, decorators, response, status
from rest_framework.exceptions import ValidationError
from .models import Backtest, BacktestStatistics
from .serializers import BacktestSerializer, BacktestStatisticsSerializer
from .services import ParameterOptimizationService, ReplayService
from trading.models.core import Strategy as StrategyModel
from trading.strategies.strategy_service import StrategyService

class BacktestViewSet(viewsets.ModelViewSet):
    serializer_class = BacktestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Backtest.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        data = self.request.data
        start_date = parse_datetime(str(data.get('start_date') or ''))
        end_date = parse_datetime(str(data.get('end_date') or ''))
        if not start_date or not end_date:
            raise ValidationError({'date_range': 'Valid start_date and end_date are required.'})
        if end_date <= start_date:
            raise ValidationError({'date_range': 'End date/time must be later than start date/time.'})
        symbol = str(data.get('symbol') or '').strip()
        timeframe = str(data.get('timeframe') or '').strip()
        strategy_name = str(data.get('strategy') or '').strip()
        if not symbol or not timeframe or not strategy_name:
            raise ValidationError({'detail': 'strategy, symbol, timeframe, start_date and end_date are required.'})
        strategy = StrategyModel.objects.filter(name__iexact=strategy_name).first()
        if not strategy:
            raise ValidationError({'strategy': 'Selected strategy does not exist in the strategy catalog.'})
        backtest = serializer.save(user=self.request.user, strategy=strategy.name, symbol=symbol, timeframe=timeframe, start_date=start_date, end_date=end_date, status='running')
        try:
            result = StrategyService.run_backtest(strategy, symbol=symbol, timeframe=timeframe, start_date=start_date, end_date=end_date)
            backtest.status = 'completed'
            backtest.result_snapshot = {'status':'completed','start_date':start_date.isoformat(),'end_date':end_date.isoformat(),'strategy':strategy.name,'symbol':symbol,'timeframe':timeframe,'result':result}
            backtest.save(update_fields=['status','result_snapshot','updated_at'])
            s = result
            stats = BacktestStatistics.objects.create(
                backtest=backtest,
                net_profit=s.get('net_profit', s.get('total_profit', 0)),
                gross_profit=s.get('gross_profit', 0), gross_loss=s.get('gross_loss', 0),
                profit_factor=0 if s.get('profit_factor') == float('inf') else s.get('profit_factor', 0),
                expectancy=s.get('expectancy', 0), win_rate=s.get('win_rate', 0), loss_rate=s.get('loss_rate', 0),
                drawdown=s.get('maximum_drawdown', s.get('max_drawdown', 0)), sharpe=s.get('sharpe_ratio', 0),
                sortino=s.get('sortino_ratio', 0), calmar=s.get('calmar_ratio', 0), metrics=s,
                equity_curve=s.get('equity_curve', []), monthly_returns=s.get('monthly_returns', {}),
            )
        except Exception as exc:
            backtest.status = 'failed'
            backtest.result_snapshot = {'status':'failed','error':str(exc),'start_date':start_date.isoformat(),'end_date':end_date.isoformat()}
            backtest.save(update_fields=['status','result_snapshot','updated_at'])
            raise

class StatisticsViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BacktestStatisticsSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_queryset(self):
        return BacktestStatistics.objects.filter(backtest__user=self.request.user)

@decorators.api_view(['POST'])
@permissions.IsAuthenticated
def paper_start(request):
    return response.Response({'status':'disabled','detail':'Paper trading is not a backtesting feature. Connect and use the broker demo account from Trading Terminal.'}, status=status.HTTP_410_GONE)

@decorators.api_view(['POST'])
@permissions.IsAuthenticated
def paper_stop(request):
    return response.Response({'status':'disabled','detail':'Paper trading is not a backtesting feature. Use the connected broker demo account from Trading Terminal.'}, status=status.HTTP_410_GONE)

@decorators.api_view(['GET'])
@permissions.IsAuthenticated
def paper_account(request):
    return response.Response({'status':'disabled','detail':'Backtesting does not create a synthetic account. Use the connected broker demo account in Trading Terminal.'}, status=status.HTTP_410_GONE)

@decorators.api_view(['POST'])
@permissions.IsAuthenticated
def optimization_start(request):
    return response.Response({'status':'started','results':ParameterOptimizationService().optimize(request.data.get('optimizer','grid'), request.data.get('space',{'x':[1]}))})

@decorators.api_view(['GET'])
@permissions.IsAuthenticated
def optimization_results(request): return response.Response({'results':[]})

@decorators.api_view(['GET'])
@permissions.IsAuthenticated
def replay(request): return response.Response(ReplayService().play())
