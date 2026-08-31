from decimal import Decimal, InvalidOperation


class CriteriaEvaluationError(ValueError):
    """Raised when a strategy criteria document cannot be evaluated safely."""


class CriteriaEngine:
    """Evaluate persisted strategy criteria against the live indicator context.

    Criteria are deliberately declarative and side-effect free. Unknown keys are
    ignored so older configurations remain compatible while the supported keys
    below provide real, deterministic gates for strategy signals.
    """

    NUMERIC_KEYS = {
        'rsi_min', 'rsi_max', 'price_min', 'price_max',
        'min_confidence', 'max_range', 'min_range',
    }

    def _number(self, value, key):
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise CriteriaEvaluationError(f'Criteria {key!r} must be numeric')

    def evaluate(self, criteria, market_data, indicator_data, signal='HOLD', confidence=0):
        if criteria in (None, {}):
            return True, []
        if not isinstance(criteria, dict):
            raise CriteriaEvaluationError('Criteria must be a JSON object')

        reasons = []
        indicators = indicator_data or {}
        market = market_data or {}

        if 'rsi_min' in criteria and self._number(indicators.get('rsi', 50), 'rsi_min') < self._number(criteria['rsi_min'], 'rsi_min'):
            reasons.append('RSI is below rsi_min')
        if 'rsi_max' in criteria and self._number(indicators.get('rsi', 50), 'rsi_max') > self._number(criteria['rsi_max'], 'rsi_max'):
            reasons.append('RSI is above rsi_max')
        if 'price_min' in criteria and self._number(market.get('close'), 'price_min') < self._number(criteria['price_min'], 'price_min'):
            reasons.append('price is below price_min')
        if 'price_max' in criteria and self._number(market.get('close'), 'price_max') > self._number(criteria['price_max'], 'price_max'):
            reasons.append('price is above price_max')
        if 'min_confidence' in criteria and self._number(confidence, 'min_confidence') < self._number(criteria['min_confidence'], 'min_confidence'):
            reasons.append('confidence is below min_confidence')
        if 'max_range' in criteria and self._number(indicators.get('range', 0), 'max_range') > self._number(criteria['max_range'], 'max_range'):
            reasons.append('range is above max_range')
        if 'min_range' in criteria and self._number(indicators.get('range', 0), 'min_range') < self._number(criteria['min_range'], 'min_range'):
            reasons.append('range is below min_range')

        required_trend = criteria.get('trend')
        if required_trend:
            allowed = {required_trend} if isinstance(required_trend, str) else set(required_trend)
            if indicators.get('trend') not in allowed:
                reasons.append(f"trend {indicators.get('trend')!r} is not allowed")

        allowed_signals = criteria.get('allowed_signals')
        if allowed_signals and signal not in set(allowed_signals):
            reasons.append(f'signal {signal!r} is not allowed')

        return not reasons, reasons
