class RiskError(Exception): pass
class RiskRejectedError(RiskError): pass
class KillSwitchActiveError(RiskRejectedError): pass
class CircuitBreakerActiveError(RiskRejectedError): pass
class RiskRuleViolation(RiskRejectedError): pass
