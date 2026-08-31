"""Performance attribution calculations."""


class PerformanceAttributionService:
    def attribute(self, returns_by_dimension):
        if not returns_by_dimension:
            return {}

        total = sum(float(v) for v in returns_by_dimension.values())
        if total == 0:
            return {k: {"return": float(v), "contribution": 0.0} for k, v in returns_by_dimension.items()}

        return {
            k: {
                "return": float(v),
                "contribution": float(v) / total,
            }
            for k, v in returns_by_dimension.items()
        }
