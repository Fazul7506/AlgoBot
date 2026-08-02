from .models import Strategy, StrategyConfiguration, StrategyExecution, StrategyPerformance, StrategySignal
class StrategyRepository:
    def enabled(self): return Strategy.objects.filter(enabled=True)
    def for_slug(self, slug): return Strategy.objects.get(slug=slug)
    def create_or_update_catalog(self, strategy_cls):
        return Strategy.objects.update_or_create(slug=strategy_cls.slug, defaults={'name':strategy_cls.name,'description':strategy_cls.description,'category':getattr(strategy_cls,'category','AI Hybrid Strategies'),'version':strategy_cls.version,'author':getattr(strategy_cls,'author','AlgoBot'),'module_path':f'{strategy_cls.__module__}.{strategy_cls.__name__}','enabled':True})[0]
class StrategyConfigurationRepository:
    def active(self): return StrategyConfiguration.objects.select_related('strategy','user','broker_account').filter(enabled=True,strategy__enabled=True)
class StrategyExecutionRepository:
    def create(self, **kw): return StrategyExecution.objects.create(**kw)
class StrategySignalRepository:
    def create(self, **kw): return StrategySignal.objects.create(**kw)
class StrategyPerformanceRepository:
    def for_strategy(self, strategy): return StrategyPerformance.objects.get_or_create(strategy=strategy)[0]
