from .registry import REQUIRED_METHODS
from .exceptions import StrategyValidationError
from .constants import SIGNAL_TYPES
class StrategyValidationService:
    def validate_class(self, cls):
        missing=[m for m in REQUIRED_METHODS if not callable(getattr(cls,m,None))]
        if missing: raise StrategyValidationError(f'Missing methods: {missing}')
        return True
    def validate_parameters(self, parameters):
        if not isinstance(parameters, dict): raise StrategyValidationError('parameters must be an object')
        return True
    def validate_signal(self, signal):
        if signal not in SIGNAL_TYPES: raise StrategyValidationError(f'Unsupported signal {signal}')
        return True
