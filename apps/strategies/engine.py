from collections import Counter
from .models import StrategyConfiguration
from .services import StrategyExecutionService
class StrategyEngine:
    def run(self, configurations=None, market_data=None, indicator_data=None):
        configs=configurations or StrategyConfiguration.objects.filter(enabled=True,strategy__enabled=True)
        return [StrategyExecutionService().run_configuration(c, market_data, indicator_data) for c in configs]
    def resolve_conflicts(self, executions, method='highest_confidence'):
        completed=[e for e in executions if e.status=='completed']
        if not completed: return None
        if method=='majority_vote': return Counter(e.signal for e in completed).most_common(1)[0][0]
        return max(completed, key=lambda e: e.confidence).signal
