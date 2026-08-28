import importlib
from django.db import transaction
from django.utils import timezone


def _celery_app():
    module = importlib.import_module('deriv_platform.celery')
    return getattr(module, 'app', None)


def _task(fn):
    app = _celery_app()
    return app.task(fn) if app else fn


def _persist_statistics(backtest, result):
    from .models import BacktestStatistics

    BacktestStatistics.objects.update_or_create(
        backtest=backtest,
        defaults={
            'net_profit': result.get('net_profit', result.get('total_profit', 0)),
            'gross_profit': result.get('gross_profit', 0),
            'gross_loss': result.get('gross_loss', 0),
            'profit_factor': 0 if result.get('profit_factor') == float('inf') else result.get('profit_factor', 0),
            'expectancy': result.get('expectancy', 0),
            'win_rate': result.get('win_rate', 0),
            'loss_rate': result.get('loss_rate', 0),
            'drawdown': result.get('maximum_drawdown', result.get('max_drawdown', 0)),
            'sharpe': result.get('sharpe_ratio', 0),
            'sortino': result.get('sortino_ratio', 0),
            'calmar': result.get('calmar_ratio', 0),
            'metrics': result,
            'equity_curve': result.get('equity_curve', []),
            'monthly_returns': result.get('monthly_returns', {}),
        },
    )


@_task
def execute_backtest(backtest_id):
    from .models import Backtest, BacktestClusterJob
    from trading.models.core import Strategy as StrategyModel
    from trading.strategies.strategy_service import StrategyService

    backtest = Backtest.objects.select_related('user').get(pk=backtest_id)
    job = BacktestClusterJob.objects.filter(backtest=backtest).order_by('-id').first()

    # Celery retries or duplicate deliveries must never execute a finished job twice.
    if backtest.status in {'completed', 'failed', 'cancelled'}:
        return backtest.id

    started_at = timezone.now()
    backtest.status = 'running'
    backtest.result_snapshot = {
        **(backtest.result_snapshot or {}),
        'status': 'running',
        'started_at': started_at.isoformat(),
        'start_date': backtest.start_date.isoformat(),
        'end_date': backtest.end_date.isoformat(),
        'live_authority': False,
        'training_eligible': False,
    }
    backtest.save(update_fields=['status', 'result_snapshot', 'updated_at'])
    if job:
        job.status = 'running'
        job.attempts = int(job.attempts or 0) + 1
        job.locked_at = started_at
        job.save(update_fields=['status', 'attempts', 'locked_at'])

    strategy = StrategyModel.objects.filter(name__iexact=backtest.strategy).first()
    if not strategy:
        finished_at = timezone.now()
        backtest.status = 'failed'
        backtest.result_snapshot = {
            **(backtest.result_snapshot or {}),
            'status': 'failed',
            'completed_at': finished_at.isoformat(),
            'error': 'Strategy no longer exists in the strategy catalog.',
            'live_authority': False,
            'training_eligible': False,
        }
        backtest.save(update_fields=['status', 'result_snapshot', 'updated_at'])
        if job:
            job.status = 'failed'
            job.save(update_fields=['status'])
        return backtest.id

    try:
        result = StrategyService.run_backtest(
            strategy,
            symbol=backtest.symbol,
            timeframe=backtest.timeframe,
            start_date=backtest.start_date,
            end_date=backtest.end_date,
        )
        finished_at = timezone.now()
        result = dict(result or {})
        result.setdefault('strategy_confidence_scope', 'historical_research_only')
        result['training_eligible'] = True
        result['live_authority'] = False
        backtest.status = 'completed'
        backtest.result_snapshot = {
            **(backtest.result_snapshot or {}),
            'status': 'completed',
            'completed_at': finished_at.isoformat(),
            'start_date': backtest.start_date.isoformat(),
            'end_date': backtest.end_date.isoformat(),
            'strategy': strategy.name,
            'symbol': backtest.symbol,
            'timeframe': backtest.timeframe,
            'result': result,
            'training_eligible': True,
            'live_authority': False,
        }
        with transaction.atomic():
            backtest.save(update_fields=['status', 'result_snapshot', 'updated_at'])
            _persist_statistics(backtest, result)
            if job:
                job.status = 'completed'
                job.save(update_fields=['status'])
        return backtest.id
    except Exception as exc:
        finished_at = timezone.now()
        backtest.status = 'failed'
        backtest.result_snapshot = {
            **(backtest.result_snapshot or {}),
            'status': 'failed',
            'completed_at': finished_at.isoformat(),
            'start_date': backtest.start_date.isoformat(),
            'end_date': backtest.end_date.isoformat(),
            'strategy': strategy.name,
            'symbol': backtest.symbol,
            'timeframe': backtest.timeframe,
            'error': str(exc),
            'training_eligible': False,
            'live_authority': False,
        }
        backtest.save(update_fields=['status', 'result_snapshot', 'updated_at'])
        if job:
            job.status = 'failed'
            job.save(update_fields=['status'])
        return backtest.id


@_task
def run_optimization_job(*args, **kwargs):
    from .services import ParameterOptimizationService
    return ParameterOptimizationService().optimize(kwargs.get('optimizer', 'grid'), kwargs.get('space', {'x': [1]}))


@_task
def run_monte_carlo(trades, runs=100, seed=42):
    from .services import MonteCarloService
    return MonteCarloService().run(trades, runs=runs, seed=seed)


@_task
def run_walk_forward(data, window='rolling', folds=3):
    from .services import WalkForwardService
    return WalkForwardService().run(data, window=window, folds=folds)


@_task
def prepare_replay():
    return {'status': 'ready'}


@_task
def generate_dataset(events, trades, purpose='ai_training', fmt='json'):
    from .services import DatasetGeneratorService
    return DatasetGeneratorService().generate(events, trades, purpose=purpose, fmt=fmt)


@_task
def calculate_statistics(trades):
    from .services import PerformanceAnalyticsService
    return PerformanceAnalyticsService().calculate(trades)


@_task
def run_benchmark_analysis(strategy_stats, benchmarks=None):
    from .services import BenchmarkService
    return BenchmarkService().compare(strategy_stats, benchmarks=benchmarks or ('buy_hold', 'random_entries', 'baseline', 'previous_version', 'ai_strategy', 'portfolio'))
