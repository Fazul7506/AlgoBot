from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import viewsets, permissions, decorators, response, status
from rest_framework.decorators import permission_classes
from rest_framework.exceptions import ValidationError

from .models import Backtest, BacktestClusterJob, BacktestStatistics
from .serializers import BacktestSerializer, BacktestStatisticsSerializer
from .services import ParameterOptimizationService, ReplayService
from trading.models.core import Strategy as StrategyModel
from apps.market_data.models import MarketSymbol


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
        if timezone.is_naive(start_date):
            start_date = timezone.make_aware(start_date)
        if timezone.is_naive(end_date):
            end_date = timezone.make_aware(end_date)
        if end_date <= start_date:
            raise ValidationError({'date_range': 'End date/time must be later than start date/time.'})

        symbol = str(data.get('symbol') or '').strip()
        timeframe = str(data.get('timeframe') or '').strip()
        strategy_name = str(data.get('strategy') or '').strip()
        if not symbol or not timeframe or not strategy_name:
            raise ValidationError({'detail': 'strategy, symbol, timeframe, start_date and end_date are required.'})

        market = MarketSymbol.objects.filter(symbol=symbol, is_active=True, is_tradable=True).first()
        if not market:
            raise ValidationError({'symbol': 'The selected instrument is not in the active broker market catalogue.'})
        supported = [str(x).strip() for x in (market.supported_timeframes or [])]
        if timeframe not in supported:
            raise ValidationError({'timeframe': 'The selected timeframe is not supported by this broker instrument.'})

        strategy = StrategyModel.objects.filter(name__iexact=strategy_name).first()
        if not strategy:
            raise ValidationError({'strategy': 'Selected strategy does not exist in the strategy catalog.'})

        backtest = serializer.save(
            user=self.request.user,
            strategy=strategy.name,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            status='pending',
        )
        job = BacktestClusterJob.objects.create(backtest=backtest, status='pending', scheduled_at=timezone.now())
        backtest.result_snapshot = {
            'status': 'pending',
            'queued_at': timezone.now().isoformat(),
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'strategy': strategy.name,
            'symbol': symbol,
            'timeframe': timeframe,
            'job_id': job.id,
            'live_authority': False,
            'training_eligible': False,
        }
        backtest.save(update_fields=['result_snapshot', 'updated_at'])

        try:
            from .tasks import execute_backtest
            transaction.on_commit(lambda: execute_backtest.delay(backtest.pk))
        except Exception as exc:
            now = timezone.now()
            backtest.status = 'failed'
            backtest.result_snapshot = {
                **(backtest.result_snapshot or {}),
                'status': 'failed',
                'started_at': now.isoformat(),
                'completed_at': now.isoformat(),
                'error': f'Backtest worker could not be queued: {exc}',
                'live_authority': False,
                'training_eligible': False,
            }
            backtest.save(update_fields=['status', 'result_snapshot', 'updated_at'])
            job.status = 'failed'
            job.attempts = 1
            job.save(update_fields=['status', 'attempts'])


class StatisticsViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BacktestStatisticsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return BacktestStatistics.objects.filter(backtest__user=self.request.user)


@decorators.api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def paper_start(request):
    return response.Response({'status': 'disabled', 'detail': 'Paper trading is not a backtesting feature. Connect and use the broker demo account from Trading Terminal.'}, status=status.HTTP_410_GONE)


@decorators.api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def paper_stop(request):
    return response.Response({'status': 'disabled', 'detail': 'Paper trading is not a backtesting feature. Use the connected broker demo account from Trading Terminal.'}, status=status.HTTP_410_GONE)


@decorators.api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def paper_account(request):
    return response.Response({'status': 'disabled', 'detail': 'Backtesting does not create a synthetic account. Use the connected broker demo account in Trading Terminal.'}, status=status.HTTP_410_GONE)


@decorators.api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def optimization_start(request):
    return response.Response({'status': 'started', 'results': ParameterOptimizationService().optimize(request.data.get('optimizer', 'grid'), request.data.get('space', {'x': [1]}))})


@decorators.api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def optimization_results(request):
    return response.Response({'results': []})


@decorators.api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def replay(request):
    return response.Response(ReplayService().play())
