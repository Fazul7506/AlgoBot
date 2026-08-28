def validate_training_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError('Training payload must be an object')
    return payload


def validate_feature_context(context):
    # Candles are authoritative broker historical data used by the
    # candlestick feature extractor. They are not a separate AI provider.
    allowed = {'market_data', 'candles', 'indicators', 'smart_money', 'strategy', 'risk'}
    unknown = set((context or {}).keys()) - allowed
    if unknown:
        raise ValueError(f'Unsupported AI data sources: {sorted(unknown)}')
    candles = (context or {}).get('candles')
    if candles is not None and not isinstance(candles, (list, tuple)):
        raise ValueError('candles must be an array of broker OHLC records')
    return context or {}
