"""Performance summary helpers."""


class PerformanceSummaryService:
    def summarize(self, returns=None):
        returns = list(returns) if returns is not None else []
        if not returns:
            return {"average_return": 0.0, "volatility": 0.0}
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        return {
            "average_return": float(mean_return),
            "volatility": float(variance ** 0.5),
        }
