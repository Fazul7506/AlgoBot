class RiskError(Exception): pass
class RiskRejectedError(RiskError): pass
class CircuitBreakerActiveError(RiskRejectedError): pass
class RiskRuleViolation(RiskRejectedError): pass
