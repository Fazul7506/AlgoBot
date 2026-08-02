from decimal import Decimal
from .exceptions import KillSwitchActiveError, RiskRuleViolation
from .repositories import RiskRepository
from .services import KillSwitchService
class RiskValidator:
    def validate_order(self,order,profile=None):
        profile=profile or RiskRepository().profile_for_user(order.user)
        if KillSwitchService().is_active(order.user): raise KillSwitchActiveError('Kill switch is active')
        if order.stake > profile.max_risk_per_trade * getattr(order.broker_account,'balance',Decimal('0')): raise RiskRuleViolation('Maximum risk per trade exceeded')
        if order.stake > profile.max_exposure * getattr(order.broker_account,'balance',Decimal('0')): raise RiskRuleViolation('Maximum exposure exceeded')
        for rule in RiskRepository().enabled_rules(profile):
            if rule.rule_type=='max_stake_limit' and order.stake>rule.value: raise RiskRuleViolation('Maximum stake limit exceeded')
            if rule.rule_type=='minimum_balance' and getattr(order.broker_account,'balance',0)<rule.value: raise RiskRuleViolation('Minimum balance requirement not met')
        return True
