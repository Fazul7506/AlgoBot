class StrategyError(Exception): pass
class StrategyValidationError(StrategyError): pass
class StrategyRegistryError(StrategyError): pass
class StrategyExecutionError(StrategyError): pass
class StrategyPermissionError(StrategyError): pass
