"""Portfolio benchmark calculations."""


class BenchmarkService:
    def compare(self, portfolio_return, benchmark_return, benchmark_name="benchmark", risk_free_rate=0.0):
        excess_return = float(portfolio_return) - float(benchmark_return)
        tracking_error = abs(excess_return)
        return {
            "portfolio_return": float(portfolio_return),
            "benchmark_return": float(benchmark_return),
            "benchmark_name": benchmark_name,
            "risk_free_rate": float(risk_free_rate),
            "excess_return": float(excess_return),
            "relative_return": float(excess_return),
            "tracking_error": float(tracking_error),
            "outperformance": excess_return > 0,
            "alpha": float(excess_return - risk_free_rate),
        }
