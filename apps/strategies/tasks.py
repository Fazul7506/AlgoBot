try:
    from deriv_platform.celery import app
except Exception:
    app=None
from .scheduler import StrategyScheduler
from .services import StrategyService, StrategyPerformanceService

def _task(fn): return app.task(fn) if app else fn
@_task
def discover_strategies(): return len(StrategyService().sync_catalog())
@_task
def execute_strategies(schedule=None): return len(StrategyScheduler().tick(schedule))
@_task
def calculate_strategy_performance(strategy_id):
    from .models import Strategy
    return StrategyPerformanceService().recalculate(Strategy.objects.get(id=strategy_id)).id
@_task
def optimize_strategy(strategy_id): return {'strategy_id': strategy_id, 'status': 'queued'}
@_task
def cleanup_old_execution_logs(days=30): return 0
