from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.portfolio.allocation import AllocationService
from apps.portfolio.analytics import AnalyticsService
from apps.portfolio.engine import PortfolioEngine
from apps.portfolio.services import PortfolioService


class PortfolioEngineTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="pms", password="test")
        self.portfolio = PortfolioService().create_portfolio(self.user, "Core", 10000)

    def test_engine_dashboard_and_allocation(self):
        AllocationService().allocate(self.portfolio, [{"strategy": "alpha", "symbol": "EURUSD", "allocation_percent": 50}])
        dashboard = PortfolioEngine().dashboard(self.portfolio)
        self.assertEqual(dashboard["name"], "Core")
        self.assertEqual(len(dashboard["allocation"]), 1)

    def test_analytics_metrics(self):
        metrics = AnalyticsService().calculate([0.01, -0.02, 0.03], [100, 98, 105])
        self.assertIn("sharpe_ratio", metrics)
        self.assertGreaterEqual(metrics["maximum_drawdown"], 0)
