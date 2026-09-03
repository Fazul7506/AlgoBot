"""Portfolio benchmark calculations."""

import math
import statistics


class BenchmarkService:
    def compare(self, portfolio_return, benchmark_return, benchmark_name="benchmark", risk_free_rate=0.0):
        portfolio = self._series(portfolio_return)
        benchmark = self._series(benchmark_return)
        if len(portfolio) == 1 and len(benchmark) == 1:
            excess_return = portfolio[0] - benchmark[0]
            tracking_error = abs(excess_return)
            observations = 1
        else:
            observations = min(len(portfolio), len(benchmark))
            if not observations:
                raise ValueError("Portfolio and benchmark returns are required")
            excess = [left - right for left, right in zip(portfolio[:observations], benchmark[:observations])]
            excess_return = statistics.mean(excess)
            tracking_error = statistics.pstdev(excess) if observations > 1 else abs(excess_return)
        return {
            "portfolio_return": float(portfolio[0]) if len(portfolio) == 1 else statistics.mean(portfolio),
            "benchmark_return": float(benchmark[0]) if len(benchmark) == 1 else statistics.mean(benchmark),
            "benchmark_name": benchmark_name,
            "risk_free_rate": float(risk_free_rate),
            "excess_return": float(excess_return),
            "relative_return": float(excess_return),
            "tracking_error": float(tracking_error),
            "outperformance": excess_return > 0,
            "alpha": float(excess_return - risk_free_rate),
            "observations": observations,
            "annualized_tracking_error": float(tracking_error * math.sqrt(252)) if observations > 1 else float(tracking_error),
        }

    @staticmethod
    def _series(value):
        if isinstance(value, (list, tuple)):
            return [float(item) for item in value]
        return [float(value)]
