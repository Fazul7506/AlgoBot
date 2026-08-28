def validate_training_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError('Training payload must be an object')
    return payload


def validate_feature_context(context):
    """Validate the structured context accepted by the AI feature pipeline.

    Candles are a first-class historical/price-action source.  They are already
    consumed by FeatureEngineeringService, so rejecting the key at this
    boundary made the production AI path fail even though the feature engine
    explicitly supported it.
    """
    allowed = {'market_data', 'candles', 'indicators', 'smart_money', 'strategy', 'risk'}
    unknown = set((context or {}).keys()) - allowed
    if unknown:
        raise ValueError(f'Unsupported AI data sources: {sorted(unknown)}')
    return context or {}
