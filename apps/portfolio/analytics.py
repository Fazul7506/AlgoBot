from math import sqrt


def safe_divide(a, b):
    return 0 if not b else a / b


class AnalyticsService:
    def calculate(self, returns=None, equity_curve=None, benchmark_returns=None):
        returns = [float(r) for r in (returns or [])]
        equity_curve = [float(v) for v in (equity_curve or [])]
        total = sum(returns)
        gains = sum(r for r in returns if r > 0)
        losses = abs(sum(r for r in returns if r < 0))
        mean = safe_divide(total, len(returns))
        volatility = sqrt(safe_divide(sum((r - mean) ** 2 for r in returns), max(len(returns) - 1, 1))) if returns else 0
        downside = [min(0, r) for r in returns]
        downside_dev = sqrt(safe_divide(sum(d * d for d in downside), len(downside))) if downside else 0
        peak = equity_curve[0] if equity_curve else 0
        max_dd = 0
        drawdowns = []
        for value in equity_curve:
            peak = max(peak, value)
            dd = safe_divide(peak - value, peak)
            drawdowns.append(dd)
            max_dd = max(max_dd, dd)
        beta = alpha = tracking_error = 0
        if benchmark_returns:
            benchmark_returns = [float(r) for r in benchmark_returns]
            n = min(len(returns), len(benchmark_returns))
            r, b = returns[:n], benchmark_returns[:n]
            bm = safe_divide(sum(b), n)
            rm = safe_divide(sum(r), n)
            var_b = sum((x - bm) ** 2 for x in b)
            beta = safe_divide(sum((r[i] - rm) * (b[i] - bm) for i in range(n)), var_b)
            alpha = rm - beta * bm
            tracking_error = sqrt(safe_divide(sum((r[i] - b[i]) ** 2 for i in range(n)), n))
        return {
            "net_profit": total, "gross_profit": gains, "gross_loss": losses,
            "roi": total, "roe": total, "annual_return": mean * 252,
            "monthly_return": mean * 21, "weekly_return": mean * 5, "daily_return": mean,
            "volatility": volatility, "risk_score": min(100, round(volatility * 1000, 2)),
            "expectancy": mean, "profit_factor": safe_divide(gains, losses),
            "recovery_factor": safe_divide(total, max_dd), "sharpe_ratio": safe_divide(mean, volatility) * sqrt(252) if volatility else 0,
            "sortino_ratio": safe_divide(mean, downside_dev) * sqrt(252) if downside_dev else 0,
            "calmar_ratio": safe_divide(mean * 252, max_dd), "treynor_ratio": safe_divide(mean, beta),
            "information_ratio": safe_divide(alpha, tracking_error), "omega_ratio": safe_divide(gains, losses),
            "maximum_drawdown": max_dd, "average_drawdown": safe_divide(sum(drawdowns), len(drawdowns)),
            "ulcer_index": sqrt(safe_divide(sum(d*d for d in drawdowns), len(drawdowns))) if drawdowns else 0,
            "value_at_risk": sorted(returns)[int(len(returns)*0.05)] if returns else 0,
            "expected_shortfall": safe_divide(sum(sorted(returns)[:max(1, int(len(returns)*0.05))]), max(1, int(len(returns)*0.05))) if returns else 0,
            "beta": beta, "alpha": alpha, "jensen_alpha": alpha, "tracking_error": tracking_error,
            "skewness": 0, "kurtosis": 0,
        }
