import importlib
import logging
import os
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation

log = logging.getLogger(__name__)


def _celery_app():
    module = importlib.import_module('deriv_platform.celery')
    return getattr(module, 'app', None)


def _task(fn):
    app = _celery_app()
    return app.task(fn) if app else fn


def _strategy_confidence(result):
    """Research score only; never grants live-trading authority."""
    trades = int(result.get('total_trades', 0) or 0)
    win_rate = float(result.get('win_rate', 0) or 0)
    if win_rate > 1:
        win_rate /= 100.0
    pf = float(result.get('profit_factor', 0) or 0)
    sharpe = float(result.get('sharpe_ratio', 0) or 0)
    drawdown = abs(float(result.get('max_drawdown', result.get('maximum_drawdown', 0)) or 0))
    sample_score = min(1.0, trades / 100.0)
    pf_score = min(1.0, max(0.0, pf / 2.0)) if pf != float('inf') else 1.0
    sharpe_score = min(1.0, max(0.0, (sharpe + 1.0) / 3.0))
    dd_score = 1.0 / (1.0 + drawdown / 100.0)
    score = 100.0 * (0.35 * win_rate + 0.25 * pf_score + 0.15 * sharpe_score + 0.15 * dd_score + 0.10 * sample_score)
    return round(max(0.0, min(100.0, score)), 2)


def _decimal(value, default='0'):
    try:
        return Decimal(str(value if value is not None else default))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _trade_datetime(value):
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt_timezone.utc)
    try:
        return datetime.fromtimestamp(float(value), tz=dt_timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _cluster_update(backtest_id, **fields):
    from .models import BacktestClusterJob
    if fields:
        BacktestClusterJob.objects.filter(backtest_id=backtest_id).update(**fields)


def _persist_trades(backtest, result):
    from .models import BacktestTrade

    BacktestTrade.objects.filter(backtest=backtest).delete()
    rows = []
    for raw in result.get('trades', []) or []:
        if not isinstance(raw, dict):
            continue
        entry_time = _trade_datetime(raw.get('entry_epoch', raw.get('entry_time')))
        if not entry_time:
            continue
        exit_time = _trade_datetime(raw.get('exit_epoch', raw.get('exit_time')))
        direction = str(raw.get('direction', raw.get('side', 'long'))).lower()
        direction = 'short' if direction in {'short', 'sell', 'put'} else 'long'
        duration = (exit_time - entry_time) if exit_time else None
        rows.append(BacktestTrade(
            backtest=backtest,
            entry_time=entry_time,
            exit_time=exit_time,
            entry_price=_decimal(raw.get('entry_price')),
            exit_price=_decimal(raw.get('exit_price')) if raw.get('exit_price') is not None else None,
            direction=direction,
            profit=_decimal(raw.get('profit', raw.get('pnl', 0))),
            fees=_decimal(raw.get('fees', 0)),
            duration=duration,
            metadata=raw,
        ))
    if rows:
        BacktestTrade.objects.bulk_create(rows, batch_size=500)
    return len(rows)


def _persist_statistics(backtest, result):
    from .models import BacktestStatistics
    pf = result.get('profit_factor', 0)
    if pf == float('inf'):
        pf = 0
    return BacktestStatistics.objects.update_or_create(
        backtest=backtest,
        defaults={
            'net_profit': result.get('net_profit', result.get('total_profit', 0)),
            'gross_profit': result.get('gross_profit', 0),
            'gross_loss': result.get('gross_loss', 0),
            'profit_factor': pf,
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
    from django.db import transaction
    from django.db.models import F
    from django.utils import timezone
    from .models import Backtest
    from apps.strategies.models import Strategy as StrategyModel
    from apps.strategies.services import StrategyService

    backtest = Backtest.objects.get(pk=backtest_id)
    _cluster_update(
        backtest_id,
        status='running',
        worker_id=os.getenv('HOSTNAME', 'celery-worker')[:120],
        locked_at=timezone.now(),
        attempts=F('attempts') + 1,
    )
    strategy = StrategyModel.objects.filter(name__iexact=backtest.strategy).first()
    if not strategy:
        backtest.status = 'failed'
        backtest.result_snapshot = {'status': 'failed', 'code': 'STRATEGY_NOT_FOUND', 'error': 'Strategy no longer exists in the strategy catalog.', 'start_date': backtest.start_date.isoformat(), 'end_date': backtest.end_date.isoformat()}
        backtest.save(update_fields=['status', 'result_snapshot', 'updated_at'])
        _cluster_update(backtest_id, status='failed', locked_at=None)
        return backtest.id
    try:
        backtest.status = 'running'
        backtest.save(update_fields=['status', 'updated_at'])
        result = StrategyService.run_backtest(strategy, symbol=backtest.symbol, timeframe=backtest.timeframe, start_date=backtest.start_date, end_date=backtest.end_date, mode=backtest.mode)
        result = result if isinstance(result, dict) else {}
        confidence = _strategy_confidence(result)
        result['strategy_confidence'] = confidence
        result['research_training'] = {'eligible': bool(result.get('total_trades', 0)), 'purpose': 'ai_training_research_only', 'live_authority': False, 'source': 'completed_historical_backtest'}
        with transaction.atomic():
            trade_count = _persist_trades(backtest, result)
            _persist_statistics(backtest, result)
            result['persisted_trade_count'] = trade_count
            backtest.status = 'completed'
            backtest.result_snapshot = {'status': 'completed', 'start_date': backtest.start_date.isoformat(), 'end_date': backtest.end_date.isoformat(), 'strategy': strategy.name, 'symbol': backtest.symbol, 'timeframe': backtest.timeframe, 'result': result}
            backtest.save(update_fields=['status', 'result_snapshot', 'updated_at'])
            _cluster_update(backtest_id, status='completed', locked_at=None)
        return backtest.id
    except Exception as exc:
        backtest.status = 'failed'
        backtest.result_snapshot = {'status': 'failed', 'code': 'BACKTEST_EXECUTION_FAILED', 'error': f'{exc.__class__.__name__}: {exc}', 'start_date': backtest.start_date.isoformat(), 'end_date': backtest.end_date.isoformat()}
        backtest.save(update_fields=['status', 'result_snapshot', 'updated_at'])
        _cluster_update(backtest_id, status='failed', locked_at=None)
        log.exception('Backtest worker failed', extra={'backtest_id': backtest_id})
        raise


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
