"""Portfolio validation helpers."""


class PortfolioValidationService:
    def validate_weights(self, weights):
        if not weights:
            return False
        total = sum(float(v) for v in weights.values())
        return abs(total - 1.0) < 1e-6
