"""Portfolio benchmark calculations with strict finite-series validation."""

import math
import statistics


class BenchmarkService:
    def compare(self, portfolio_return, benchmark_return, benchmark_name="benchmark", risk_free_rate=0.0):
        portfolio = self._series(portfolio_return, "portfolio_return")
        benchmark = self._series(benchmark_return, "benchmark_return")
        risk_free = self._finite(risk_free_rate, "risk_free_rate")
        if len(portfolio) != len(benchmark):
            raise ValueError("Portfolio and benchmark series must have the same number of observations.")
        if isinstance(benchmark_name, str):
            benchmark_name = benchmark_name.strip()[:80] or "benchmark"
        else:
            raise ValueError("benchmark_name must be text.")

        if len(portfolio) == 1:
            excess_return = portfolio[0] - benchmark[0]
            tracking_error = abs(excess_return)
            observations = 1
        else:
            observations = len(portfolio)
            excess = [left - right for left, right in zip(portfolio, benchmark)]
            excess_return = statistics.mean(excess)
            tracking_error = statistics.pstdev(excess)

        return {
            "portfolio_return": float(portfolio[0]) if len(portfolio) == 1 else statistics.mean(portfolio),
            "benchmark_return": float(benchmark[0]) if len(benchmark) == 1 else statistics.mean(benchmark),
            "benchmark_name": benchmark_name,
            "risk_free_rate": risk_free,
            "excess_return": float(excess_return),
            "relative_return": float(excess_return),
            "tracking_error": float(tracking_error),
            "outperformance": excess_return > 0,
            "alpha": float(excess_return - risk_free),
            "observations": observations,
            "annualized_tracking_error": float(tracking_error * math.sqrt(252)) if observations > 1 else float(tracking_error),
        }

    @classmethod
    def _series(cls, value, field):
        values = list(value) if isinstance(value, (list, tuple)) else [value]
        if not values:
            raise ValueError(f"{field} must contain at least one observation.")
        return [cls._finite(item, field) for item in values]

    @staticmethod
    def _finite(value, field):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{field} must contain finite numeric observations.") from exc
        if not math.isfinite(number):
            raise ValueError(f"{field} must contain finite numeric observations.")
        return number
