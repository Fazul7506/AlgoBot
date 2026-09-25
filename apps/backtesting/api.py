import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import viewsets, permissions, decorators, response, status
from rest_framework.decorators import permission_classes
from rest_framework.exceptions import ValidationError
from .models import Backtest, BacktestClusterJob, BacktestStatistics
from .serializers import BacktestSerializer, BacktestStatisticsSerializer, BacktestTradeSerializer, canonical_timeframe
from .services import ParameterOptimizationService, ReplayService
from apps.strategies.models import Strategy as StrategyModel
from apps.market_data.models import MarketSymbol, Tick
from apps.market_data.constants import TIMEFRAMES
from apps.market_data.research_data import ResearchDataService
from core.billing_entitlements import check, effective_plan

log = logging.getLogger(__name__)


class BacktestViewSet(viewsets.ModelViewSet):
    serializer_class = BacktestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Backtest.objects.filter(user=self.request.user)

    def _queue(self, backtest):
        """Create a durable queue record and publish without holding a DB lock.

        Publishing a Celery message inside the create/update transaction can
        block the HTTP request on a dead Redis connection. It also lets a fast
        worker observe an uncommitted Backtest row. Persist first, then publish.
        """
        from .tasks import execute_backtest

        BacktestClusterJob.objects.update_or_create(
            backtest=backtest,
            defaults={
                'priority': 5,
                'worker_id': '',
                'attempts': 0,
                'status': 'pending',
                'scheduled_at': timezone.now(),
                'locked_at': None,
            },
        )

        if not getattr(settings, 'USE_CELERY', True) or not hasattr(execute_backtest, 'apply_async'):
            detail = 'Backtest worker is not configured. Start the Celery worker before running historical tests.'
            backtest.status = 'failed'
            backtest.result_snapshot = {
                'status': 'failed',
                'code': 'BACKTEST_WORKER_UNAVAILABLE',
                'error': detail,
                'start_date': backtest.start_date.isoformat(),
                'end_date': backtest.end_date.isoformat(),
            }
            backtest.save(update_fields=['status', 'result_snapshot', 'updated_at'])
            BacktestClusterJob.objects.filter(backtest=backtest).update(status='failed', locked_at=None)
            return False

        backtest.status = 'pending'
        backtest.save(update_fields=['status', 'updated_at'])
        try:
            execute_backtest.apply_async(args=(backtest.pk,), retry=False)
            return True
        except Exception as exc:
            detail = f'{exc.__class__.__name__}: {exc}'
            log.exception('Unable to publish backtest job', extra={'backtest_id': backtest.pk})
            backtest.status = 'failed'
            backtest.result_snapshot = {
                'status': 'failed',
                'code': 'BACKTEST_QUEUE_UNAVAILABLE',
                'error': detail,
                'start_date': backtest.start_date.isoformat(),
                'end_date': backtest.end_date.isoformat(),
            }
            backtest.save(update_fields=['status', 'result_snapshot', 'updated_at'])
            BacktestClusterJob.objects.filter(backtest=backtest).update(status='failed', locked_at=None)
            return False

    def perform_create(self, serializer):
        allowed, used, limit = check(self.request.user, 'backtests')
        if not allowed:
            plan = effective_plan(self.request.user)
            raise ValidationError({'detail': f'Your {plan.name} backtest allowance has been reached for today.', 'code': 'BACKTEST_LIMIT_REACHED', 'plan': plan.key, 'used': used, 'limit': limit})

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
        if end_date > timezone.now():
            raise ValidationError({'end_date': 'Backtests are historical only; end date/time cannot be in the future.'})

        symbol = str(data.get('symbol') or '').strip().upper()
        timeframe = canonical_timeframe(data.get('timeframe'))
        strategy_id = data.get('strategy_id')
        strategy_ref = str(data.get('strategy') or data.get('strategy_slug') or '').strip()
        if not symbol or not timeframe or not (strategy_id or strategy_ref):
            raise ValidationError({'detail': 'strategy, symbol, timeframe, start_date and end_date are required.'})
        market = MarketSymbol.objects.filter(symbol=symbol, is_active=True, is_tradable=True).first()
        if not market:
            raise ValidationError({'symbol': 'The selected instrument is not in the active broker market catalogue.'})
        if timeframe not in TIMEFRAMES:
            raise ValidationError({'timeframe': f'The selected timeframe is not supported by AlgoBot. Supported values: {", ".join(TIMEFRAMES.keys())}.'})

        strategy = None
        if strategy_id:
            try:
                strategy = StrategyModel.objects.filter(pk=int(strategy_id), enabled=True).first()
            except (TypeError, ValueError):
                strategy = None
        if strategy is None and strategy_ref:
            strategy = StrategyModel.objects.filter(slug__iexact=strategy_ref, enabled=True).first() or StrategyModel.objects.filter(name__iexact=strategy_ref, enabled=True).first()
        if not strategy:
            raise ValidationError({'strategy': 'Selected strategy does not exist in the enabled strategy catalog.'})

        mode = str(data.get('mode') or 'candle_close').strip().lower()
        if mode not in {'candle_close', 'tick'}:
            raise ValidationError({'mode': 'Execution mode must be candle_close or tick.'})

        # Strategy indicators need warm-up observations, but the user-selected
        # interval is the evaluation window. Do not require 21 candles/ticks to
        # exist *inside* a short research window such as one hour of 15m data.
        # The worker loads the preceding warm-up history separately and only
        # records trades whose entry/exit timestamps remain inside this exact
        # interval.
        start_epoch = int(start_date.timestamp())
        end_epoch = int(end_date.timestamp())
        min_history = 20
        if mode == 'tick':
            warmup_count = Tick.objects.filter(
                symbol=market, epoch__lt=start_epoch
            ).order_by('-epoch', '-id').values('id')[:min_history].count()
            evaluation_count = Tick.objects.filter(
                symbol=market, epoch__gte=start_epoch, epoch__lte=end_epoch
            ).count()
            if warmup_count < min_history or evaluation_count < 2:
                raise ValidationError({'date_range': f'Insufficient persisted tick history for this evaluation window. AlgoBot needs {min_history} earlier ticks for indicator warm-up and at least 2 ticks inside the selected interval; found {warmup_count} warm-up ticks and {evaluation_count} evaluation ticks.'})
        else:
            research_data = ResearchDataService()
            try:
                warmup_count = research_data.count(
                    market.symbol,
                    timeframe,
                    end_epoch=start_epoch - 1,
                )
                evaluation_count = research_data.count(
                    market.symbol,
                    timeframe,
                    start_epoch=start_epoch,
                    end_epoch=end_epoch,
                )
            except ValueError as exc:
                raise ValidationError({'date_range': str(exc)}) from exc
            if warmup_count < min_history or evaluation_count < 2:
                raise ValidationError({'date_range': f'Insufficient persisted {timeframe} candle history for this evaluation window. AlgoBot needs {min_history} earlier candles for indicator warm-up and at least 2 candles inside the selected interval; found {warmup_count} warm-up candles and {evaluation_count} evaluation candles.'})

        with transaction.atomic():
            user_model = self.request.user.__class__
            user_model.objects.select_for_update().get(pk=self.request.user.pk)
            duplicate = Backtest.objects.filter(
                user=self.request.user, strategy=strategy.name, symbol=symbol, timeframe=timeframe,
                start_date=start_date, end_date=end_date, mode=mode, status__in=['pending', 'running']
            ).first()
            if duplicate:
                raise ValidationError({'detail': 'An identical backtest is already queued or running.', 'code': 'DUPLICATE_BACKTEST', 'id': duplicate.pk})
            backtest = serializer.save(user=self.request.user, strategy=strategy.name, symbol=symbol, timeframe=timeframe, start_date=start_date, end_date=end_date, mode=mode, status='pending')

        self._queue(backtest)

    def perform_update(self, serializer):
        instance = self.get_object()
        with transaction.atomic():
            backtest = serializer.save(
                status='pending',
                result_snapshot={},
                result_version=instance.result_version + 1,
            )
            backtest.trades.all().delete()
            BacktestStatistics.objects.filter(backtest=backtest).delete()
        self._queue(backtest)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        instance = self.get_queryset().get(pk=serializer.instance.pk)
        return response.Response(self.get_serializer(instance).data, status=status.HTTP_202_ACCEPTED, headers=self.get_success_headers(serializer.data))

    @decorators.action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        backtest = self.get_object()
        if backtest.status not in {'pending', 'running'}:
            raise ValidationError({'status': 'Only pending or running backtests can be cancelled.'})
        backtest.status = 'cancelled'
        backtest.result_snapshot = {**(backtest.result_snapshot or {}), 'status': 'cancelled', 'error': 'Cancelled by user.'}
        backtest.save(update_fields=['status', 'result_snapshot', 'updated_at'])
        BacktestClusterJob.objects.filter(backtest=backtest, status__in=['pending', 'running']).update(status='cancelled', locked_at=None)
        return response.Response(self.get_serializer(backtest).data)

    @decorators.action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        backtest = self.get_object()
        if backtest.status not in {'failed', 'cancelled'}:
            raise ValidationError({'status': 'Only failed or cancelled backtests can be retried.'})
        with transaction.atomic():
            backtest.status = 'pending'
            backtest.result_snapshot = {}
            backtest.result_version += 1
            backtest.save(update_fields=['status', 'result_snapshot', 'result_version', 'updated_at'])
        self._queue(backtest)
        return response.Response(self.get_serializer(backtest).data, status=status.HTTP_202_ACCEPTED)

    @decorators.action(detail=True, methods=['get'])
    def results(self, request, pk=None):
        backtest = self.get_object()
        data = self.get_serializer(backtest).data
        data['trades'] = BacktestTradeSerializer(backtest.trades.all(), many=True).data
        statistics = getattr(backtest, 'statistics', None)
        data['statistics'] = BacktestStatisticsSerializer(statistics).data if statistics else None
        return response.Response(data)


class StatisticsViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BacktestStatisticsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return BacktestStatistics.objects.filter(backtest__user=self.request.user)


@decorators.api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def optimization_start(request):
    allowed, used, limit = check(request.user, 'backtests')
    if not allowed:
        plan = effective_plan(request.user); return response.Response({'status':'rejected','code':'BACKTEST_LIMIT_REACHED','detail':f'Your {plan.name} backtest allowance has been reached for today.','plan':plan.key,'used':used,'limit':limit}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    return response.Response({'status':'started','results':ParameterOptimizationService().optimize(request.data.get('optimizer','grid'), request.data.get('space',{'x':[1]}))})

@decorators.api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def optimization_results(request): return response.Response({'results':[]})

@decorators.api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def replay(request): return response.Response(ReplayService().play())
