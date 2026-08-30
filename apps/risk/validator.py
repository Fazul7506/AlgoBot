from decimal import Decimal, InvalidOperation

from .exceptions import KillSwitchActiveError, RiskRuleViolation
from .repositories import RiskRepository
from .services import KillSwitchService


class RiskValidator:
    """Fail-closed pre-trade risk validation at the execution boundary."""

    @staticmethod
    def _decimal(value, field_name):
        try:
            result = Decimal(str(value or 0))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise RiskRuleViolation(f"Invalid {field_name}") from exc
        if not result.is_finite():
            raise RiskRuleViolation(f"Invalid {field_name}")
        return result

    def validate_order(self, order, profile=None):
        profile = profile or RiskRepository().profile_for_user(order.user)
        if KillSwitchService().is_active(order.user):
            raise KillSwitchActiveError("Kill switch is active")

        account = getattr(order, "account", None)
        balance = self._decimal(getattr(account, "balance", 0), "account balance")
        stake = self._decimal(getattr(order, "stake", 0), "stake")
        if stake <= 0:
            raise RiskRuleViolation("Stake must be greater than zero")
        if balance <= 0:
            raise RiskRuleViolation("Account balance must be greater than zero")

        max_risk_per_trade = self._decimal(getattr(profile, "max_risk_per_trade", 0), "max risk per trade")
        max_exposure = self._decimal(getattr(profile, "max_exposure", 0), "max exposure")
        if max_risk_per_trade < 0 or max_exposure < 0:
            raise RiskRuleViolation("Risk profile limits cannot be negative")
        if stake > max_risk_per_trade * balance:
            raise RiskRuleViolation("Maximum risk per trade exceeded")
        if stake > max_exposure * balance:
            raise RiskRuleViolation("Maximum exposure exceeded")

        repository = RiskRepository()
        for rule in repository.enabled_rules(profile):
            rule_value = self._decimal(getattr(rule, "value", 0), "risk rule value")
            if rule_value < 0:
                raise RiskRuleViolation("Risk rule values cannot be negative")
            if rule.rule_type == "max_stake_limit" and stake > rule_value:
                raise RiskRuleViolation("Maximum stake limit exceeded")
            if rule.rule_type == "minimum_balance" and balance < rule_value:
                raise RiskRuleViolation("Minimum balance requirement not met")
        return True
