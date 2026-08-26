from decimal import Decimal

from .exceptions import KillSwitchActiveError, RiskRuleViolation
from .repositories import RiskRepository
from .services import KillSwitchService


class RiskValidator:
    def validate_order(self, order, profile=None):
        profile = profile or RiskRepository().profile_for_user(order.user)
        if KillSwitchService().is_active(order.user):
            raise KillSwitchActiveError('Kill switch is active')

        account = getattr(order, 'account', None)
        balance = Decimal(str(getattr(account, 'balance', 0) or 0))
        stake = Decimal(str(getattr(order, 'stake', 0) or 0))

        # RiskProfile/RiskRule normally expose DecimalField values, but callers
        # and test fixtures can provide native floats. Normalize every numeric
        # risk limit at the validation boundary so Decimal arithmetic never
        # mixes with float values.
        max_risk_per_trade = Decimal(str(getattr(profile, 'max_risk_per_trade', 0) or 0))
        max_exposure = Decimal(str(getattr(profile, 'max_exposure', 0) or 0))
        if stake > max_risk_per_trade * balance:
            raise RiskRuleViolation('Maximum risk per trade exceeded')
        if stake > max_exposure * balance:
            raise RiskRuleViolation('Maximum exposure exceeded')

        for rule in RiskRepository().enabled_rules(profile):
            rule_value = Decimal(str(getattr(rule, 'value', 0) or 0))
            if rule.rule_type == 'max_stake_limit' and stake > rule_value:
                raise RiskRuleViolation('Maximum stake limit exceeded')
            if rule.rule_type == 'minimum_balance' and balance < rule_value:
                raise RiskRuleViolation('Minimum balance requirement not met')
        return True
