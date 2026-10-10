import logging

logger = logging.getLogger(__name__)

try:
    from deriv_platform.celery import app
except Exception:
    logger.warning("Strategy task Celery app import failed; falling back to synchronous task execution.", exc_info=True)
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