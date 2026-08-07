from .allocation import AllocationService
from .analytics import AnalyticsService
from .benchmark import BenchmarkService
from .correlation import CorrelationService
from .diversification import DiversificationService
from .exposure import ExposureService
from .forecasting import ForecastingService
from .optimization import OptimizationService
from .rebalancing import RebalancingService
from .reporting import ReportingService
from .services import CashFlowService, PerformanceService, PortfolioService


class PortfolioEngine:
    def __init__(self):
        self.portfolios = PortfolioService()
        self.allocation = AllocationService()
        self.optimization = OptimizationService()
        self.diversification = DiversificationService()
        self.correlation = CorrelationService()
        self.exposure = ExposureService()
        self.analytics = AnalyticsService()
        self.performance = PerformanceService()
        self.benchmark = BenchmarkService()
        self.forecasting = ForecastingService()
        self.reporting = ReportingService()
        self.cashflow = CashFlowService()
        self.rebalancing = RebalancingService()

    def dashboard(self, portfolio):
        latest_performance = portfolio.performance.first()
        return {
            "id": portfolio.id,
            "name": portfolio.name,
            "net_asset_value": portfolio.net_asset_value,
            "equity": portfolio.equity,
            "balance": portfolio.current_balance,
            "allocation": list(portfolio.allocations.values("strategy", "symbol", "allocation_percent", "allocated_capital")),
            "exposure": self.exposure.summarize(portfolio.exposures.all()),
            "performance": latest_performance.metrics if latest_performance else {},
            "forecast": portfolio.forecasts.order_by("-generated_at").values("forecast_period", "expected_return", "expected_drawdown", "confidence").first(),
            "rebalancing_suggestions": self.rebalancing.suggestions(portfolio),
        }
