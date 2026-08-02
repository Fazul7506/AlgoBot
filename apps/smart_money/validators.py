from .exceptions import InvalidMarketData

def validate_candles(candles):
    if not candles or len(candles) < 3:
        raise InvalidMarketData('At least three OHLCV candles are required')
    for c in candles:
        for k in ('open','high','low','close'):
            if k not in c:
                raise InvalidMarketData(f'Missing {k}')
        if float(c['high']) < float(c['low']):
            raise InvalidMarketData('Candle high cannot be below low')
    return True

def clamp_score(value):
    return max(0.0, min(100.0, float(value)))
