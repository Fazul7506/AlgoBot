import importlib
import logging
import os
from datetime import datetime, timezone as dt_timezone, timedelta
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


def _warmup_start(backtest, minimum_history=20):
    """Return the timestamp of the oldest persisted warm-up observation before start."""
    start_epoch = int(backtest.start_date.timestamp())
    if str(backtest.mode).lower() == 'tick':
        from apps.market_data.models import Tick
        epochs = list(
            Tick.objects.filter(symbol__symbol=backtest.symbol, epoch__lt=start_epoch)
            .order_by('-epoch', '-id')
            .values_list('epoch', flat=True)[:minimum_history]
        )
    else:
        from apps.market_data.research_data import ResearchDataService
        epochs = [
            row['epoch']
            for row in ResearchDataService().previous_candles(
                backtest.symbol,
                backtest.timeframe,
                before_epoch=start_epoch,
                limit=minimum_history,
            )
        ]
    if len(epochs) < minimum_history:
        raise ValueError(
            f'Insufficient historical warm-up data before the selected start: '
            f'found {len(epochs)}, need {minimum_history}.'
        )
    return datetime.fromtimestamp(min(epochs), tz=dt_timezone.utc)


def _window_result(result, start_epoch, end_epoch):
    """Remove warm-up trades and recompute research metrics for the exact window."""
    trades = []
    for trade in result.get('trades', []) or []:
        try:
            entry = int(float(trade.get('entry_epoch')))
            exit_epoch = int(float(trade.get('exit_epoch')))
        except (TypeError, ValueError):
            continue
        if entry >= start_epoch and exit_epoch <= end_epoch:
            trades.append(trade)

    profits = [float(trade.get('profit', trade.get('pnl', 0)) or 0) for trade in trades]
    wins = sum(p > 0 for p in profits)
    losses = sum(p < 0 for p in profits)
    total_profit = float(sum(profits))
    gross_profit = float(sum(p for p in profits if p > 0))
    gross_loss = float(abs(sum(p for p in profits if p < 0)))
    expectancy = total_profit / len(profits) if profits else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss else (float('inf') if gross_profit else 0.0)
    equity = [1000.0]
    for profit in profits:
        equity.append(equity[-1] + profit)
    max_drawdown = max((max(equity[:i + 1]) - equity[i] for i in range(len(equity))), default=0.0)

    return {
        **result,
        'trades': trades,
        'total_trades': len(trades),
        'wins': wins,
        'losses': losses,
        'win_rate': (wins / len(trades) * 100) if trades else 0.0,
        'loss_rate': (losses / len(trades) * 100) if trades else 0.0,
        'expectancy': expectancy,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'profit_factor': profit_factor,
        'total_profit': total_profit,
        'roi': total_profit / 1000 * 100,
        'max_drawdown': max_drawdown,
        'sharpe_ratio': 0,
        'sortino_ratio': 0,
        'equity_curve': equity,
        'evaluation_start_epoch': start_epoch,
        'evaluation_end_epoch': end_epoch,
        'warmup_trade_count': int(result.get('total_trades', 0) or 0) - len(trades),
    }


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
        evaluation_start_epoch = int(backtest.start_date.timestamp())
        evaluation_end_epoch = int(backtest.end_date.timestamp())
        calculation_start = _warmup_start(backtest)
        result = StrategyService.run_backtest(
            strategy,
            symbol=backtest.symbol,
            timeframe=backtest.timeframe,
            start_date=calculation_start,
            end_date=backtest.end_date,
            mode=backtest.mode,
        )
        result = _window_result(result if isinstance(result, dict) else {}, evaluation_start_epoch, evaluation_end_epoch)
        result['strategy_confidence'] = _strategy_confidence(result)
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
