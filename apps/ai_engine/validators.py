def validate_training_payload(payload):
    if not isinstance(payload, dict): raise ValueError('Training payload must be an object')
    return payload
def validate_feature_context(context):
    allowed={'market_data','indicators','smart_money','strategy','risk'}
    unknown=set((context or {}).keys())-allowed
    if unknown: raise ValueError(f'Unsupported AI data sources: {sorted(unknown)}')
    return context or {}
