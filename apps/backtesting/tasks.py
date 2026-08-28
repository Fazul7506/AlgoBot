import importlib


def _celery_app():
    module = importlib.import_module('deriv_platform.celery')
    return getattr(module, 'app', None)


def _task(fn):
    app = _celery_app()
    return app.task(fn) if app else fn


@_task
def execute_backtest(backtest_id):
    from .models import Backtest
    from trading.models.core import Strategy as StrategyModel
    from trading.strategies.strategy_service import StrategyService
    backtest = Backtest.objects.get(pk=backtest_id)
    strategy = StrategyModel.objects.filter(name__iexact=backtest.strategy).first()
    if not strategy:
        backtest.status = 'failed'; backtest.result_snapshot = {'status':'failed','error':'Strategy no longer exists in the strategy catalog.'}; backtest.save(update_fields=['status','result_snapshot','updated_at']); return backtest.id
    try:
        backtest.status = 'running'; backtest.save(update_fields=['status','updated_at'])
        result = StrategyService.run_backtest(strategy, symbol=backtest.symbol, timeframe=backtest.timeframe, start_date=backtest.start_date, end_date=backtest.end_date)
        backtest.status = 'completed'; backtest.result_snapshot = {'status':'completed','start_date':backtest.start_date.isoformat(),'end_date':backtest.end_date.isoformat(),'strategy':strategy.name,'symbol':backtest.symbol,'timeframe':backtest.timeframe,'result':result}; backtest.save(update_fields=['status','result_snapshot','updated_at'])
        return backtest.id
    except Exception as exc:
        backtest.status = 'failed'; backtest.result_snapshot = {'status':'failed','error':str(exc),'start_date':backtest.start_date.isoformat(),'end_date':backtest.end_date.isoformat()}; backtest.save(update_fields=['status','result_snapshot','updated_at']); raise


@_task
def run_optimization_job(*args, **kwargs):
    from .services import ParameterOptimizationService
    return ParameterOptimizationService().optimize(kwargs.get('optimizer', 'grid'), kwargs.get('space', {'x':[1]}))

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
    return {'status':'ready'}

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
    return BenchmarkService().compare(strategy_stats, benchmarks=benchmarks or ('buy_hold','random_entries','baseline','previous_version','ai_strategy','portfolio'))
