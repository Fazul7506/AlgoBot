from django.core.exceptions import ValidationError
from .constants import TIMEFRAMES

def validate_timeframe(timeframe):
    if timeframe not in TIMEFRAMES:
        raise ValidationError(f'Unsupported timeframe: {timeframe}')
    return timeframe

def validate_indicator_parameters(parameters):
    if parameters is None:
        return {}
    if not isinstance(parameters, dict):
        raise ValidationError('Indicator parameters must be an object')
    for key, value in parameters.items():
        if key in {'period','fast','slow','signal','length'} and int(value) <= 0:
            raise ValidationError(f'{key} must be positive')
    return parameters
