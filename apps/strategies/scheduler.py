import logging
from .repositories import StrategyConfigurationRepository
from .services import StrategyExecutionService

log=logging.getLogger(__name__)

class StrategyScheduler:
    def due_configurations(self, schedule=None):
        qs=StrategyConfigurationRepository().active()
        return qs.filter(schedule=schedule) if schedule else qs

    def tick(self, schedule=None):
        results=[]
        for config in self.due_configurations(schedule):
            results.append(StrategyExecutionService().run_configuration(config))
        return results
