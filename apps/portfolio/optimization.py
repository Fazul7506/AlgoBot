from .services import PortfolioService, PerformanceService, CashFlowService


class OptimizationService:
    def optimize(self, assets, method="mean_variance", constraints=None):
        assets = list(assets or [])
        weight = 1 / len(assets) if assets else 0
        return {"method": method, "weights": {asset: weight for asset in assets}, "constraints": constraints or {}}


class DiversificationService:
    def analyze(self, allocations):
        buckets = {}
        for item in allocations:
            key = getattr(item, "symbol", None) or item.get("symbol", "cash")
            buckets[key] = buckets.get(key, 0) + float(getattr(item, "allocation_percent", item.get("allocation_percent", 0)))
        return {"asset_diversification": buckets, "concentration": max(buckets.values()) if buckets else 0}


class CorrelationService:
    def matrix(self, series_by_name, method="pearson"):
        names = list(series_by_name.keys())
        return {a: {b: (1.0 if a == b else 0.0) for b in names} for a in names}


class ExposureService:
    def summarize(self, exposures):
        summary = {}
        for item in exposures:
            key = getattr(item, "market", None) or item.get("market", "unknown")
            summary[key] = summary.get(key, 0) + float(getattr(item, "exposure", item.get("exposure", 0)))
        return summary


class BenchmarkService:
    def compare(self, portfolio_return, benchmark_return):
        return {"portfolio_return": portfolio_return, "benchmark_return": benchmark_return, "excess_return": portfolio_return - benchmark_return}


class ForecastingService:
    def forecast(self, returns, period="30d"):
        returns = list(returns or [])
        expected = sum(returns) / len(returns) if returns else 0
        return {"forecast_period": period, "expected_return": expected, "expected_drawdown": min(returns) if returns else 0, "confidence": 0.75 if returns else 0.25}


class ReportingService:
    def generate(self, portfolio, report_type="executive", export_format="json"):
        return {"portfolio": portfolio.name, "report_type": report_type, "format": export_format, "nav": float(portfolio.net_asset_value)}


class RebalancingService:
    def suggestions(self, portfolio, threshold=5):
        return [{"symbol": a.symbol, "current": float(a.allocation_percent), "target": float(a.allocation_percent), "action": "hold"} for a in portfolio.allocations.all()]


class PerformanceAttributionService:
    def attribute(self, returns_by_dimension):
        total = sum(returns_by_dimension.values()) if returns_by_dimension else 0
        return {k: {"return": v, "contribution": (v / total if total else 0)} for k, v in (returns_by_dimension or {}).items()}
