from .repositories import StrategyConfigurationRepository
from .services import StrategyExecutionService
class StrategyScheduler:
    def due_configurations(self, schedule=None):
        qs=StrategyConfigurationRepository().active(); return qs.filter(schedule=schedule) if schedule else qs
    def tick(self, schedule=None): return [StrategyExecutionService().run_configuration(c) for c in self.due_configurations(schedule)]
