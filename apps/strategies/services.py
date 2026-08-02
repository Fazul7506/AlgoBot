import logging, time
from django.utils import timezone
from .registry import registry
from .repositories import StrategyRepository, StrategyExecutionRepository, StrategySignalRepository, StrategyPerformanceRepository
from .validator import StrategyValidationService
log=logging.getLogger(__name__)
class StrategyService:
    def sync_catalog(self): return [StrategyRepository().create_or_update_catalog(cls) for cls in registry.all().values()]
class StrategyExecutionService:
    def run_configuration(self, config, market_data=None, indicator_data=None):
        start=time.perf_counter(); execution=StrategyExecutionRepository().create(strategy=config.strategy,configuration=config,symbol=config.symbol,timeframe=config.timeframe,status='running')
        try:
            cls=registry.get(config.strategy.slug); strat=cls(config, market_data or {}, indicator_data or {}); strat.initialize(); strat.validate(); result=strat.execute(); StrategyValidationService().validate_signal(result['signal'])
            execution.signal=result['signal']; execution.confidence=result['confidence']; execution.status='completed'; execution.completed_at=timezone.now(); execution.latency_ms=(time.perf_counter()-start)*1000; execution.context=result; execution.save()
            StrategySignalRepository().create(strategy=config.strategy,configuration=config,symbol=config.symbol,signal=result['signal'],confidence=result['confidence'],entry_price=result.get('entry_price'),stop_loss=result.get('stop_loss'),take_profit=result.get('take_profit'),metadata=result)
            log.info('Strategy execution completed', extra={'strategy':config.strategy.slug,'signal':result['signal']}); return execution
        except Exception as exc:
            execution.status='failed'; execution.error=str(exc); execution.completed_at=timezone.now(); execution.latency_ms=(time.perf_counter()-start)*1000; execution.save(); log.exception('Strategy execution failed'); return execution
class StrategyPerformanceService:
    def recalculate(self, strategy):
        perf=StrategyPerformanceRepository().for_strategy(strategy); qs=strategy.executions.filter(status='completed').exclude(signal='HOLD'); perf.total_trades=qs.count(); perf.wins=strategy.executions.filter(context__outcome='win').count(); perf.losses=strategy.executions.filter(context__outcome='loss').count(); perf.win_rate=(perf.wins/perf.total_trades*100) if perf.total_trades else 0; perf.last_updated=timezone.now(); perf.save(); return perf
class StrategyOptimizationService: pass
class StrategyValidationService(StrategyValidationService): pass
