from collections import Counter

from django.db import transaction

from .models import StrategyConfiguration
from .services import StrategyExecutionService


class StrategyEngine:
    """Single-configuration strategy runner.

    The engine must never silently execute every enabled configuration. When no
    explicit configuration set is supplied, only the user's active
    configuration is eligible. Callers without a user must provide explicit
    configurations.
    """

    def active_configuration(self, user):
        if user is None or not getattr(user, 'is_authenticated', False):
            return None
        return (
            StrategyConfiguration.objects
            .select_related('strategy', 'broker_account', 'broker_account__broker')
            .filter(user=user, enabled=True, is_active=True, strategy__enabled=True)
            .first()
        )

    def run(self, configurations=None, user=None, market_data=None, indicator_data=None):
        if configurations is None:
            configuration = self.active_configuration(user)
            configurations = [configuration] if configuration else []

        # Materialise once so a queryset cannot change halfway through a run.
        configs = list(configurations)
        if len(configs) > 1:
            # A user has one active strategy at a time. If a caller explicitly
            # supplies several configurations, retain only the active one when
            # all records belong to the same user.
            users = {getattr(c, 'user_id', None) for c in configs}
            if len(users) == 1 and None not in users:
                active = [c for c in configs if c.enabled and c.is_active and c.strategy.enabled]
                configs = active[:1]

        return [
            StrategyExecutionService().run_configuration(c, market_data, indicator_data)
            for c in configs
            if c.enabled and c.strategy.enabled and c.is_active
        ]

    def resolve_conflicts(self, executions, method='highest_confidence'):
        completed = [e for e in executions if e.status == 'completed']
        if not completed:
            return None
        if method == 'majority_vote':
            return Counter(e.signal for e in completed).most_common(1)[0][0]
        return max(completed, key=lambda e: e.confidence).signal
