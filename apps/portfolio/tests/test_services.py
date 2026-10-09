from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.portfolio.allocation import AllocationService
from apps.portfolio.analytics import AnalyticsService
from apps.portfolio.attribution import PerformanceAttributionService
from apps.portfolio.benchmark import BenchmarkService
from apps.portfolio.engine import PortfolioEngine
from apps.portfolio.reporting import ReportingService
from apps.portfolio.rebalancing import RebalancingService
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

    def test_benchmark_metrics_are_real(self):
        result = BenchmarkService().compare(portfolio_return=0.12, benchmark_return=0.08)
        self.assertEqual(result["portfolio_return"], 0.12)
        self.assertEqual(result["benchmark_return"], 0.08)
        self.assertEqual(result["excess_return"], 0.04)
        self.assertIn("tracking_error", result)

    def test_benchmark_series_calculates_tracking_error(self):
        result = BenchmarkService().compare([0.10, 0.04], [0.08, 0.02])
        self.assertEqual(result["observations"], 2)
        self.assertAlmostEqual(result["excess_return"], 0.02)
        self.assertAlmostEqual(result["tracking_error"], 0.0)

    def test_benchmark_rejects_non_finite_returns_and_risk_free_rate(self):
        for portfolio_return, benchmark_return, risk_free_rate in (
            (float("nan"), 0.1, 0.0),
            (0.1, float("inf"), 0.0),
            (0.1, 0.05, float("-inf")),
        ):
            with self.subTest(portfolio_return=portfolio_return, benchmark_return=benchmark_return):
                with self.assertRaises(ValueError):
                    BenchmarkService().compare(
                        portfolio_return, benchmark_return, risk_free_rate=risk_free_rate
                    )

    def test_benchmark_rejects_empty_or_mismatched_series(self):
        with self.assertRaises(ValueError):
            BenchmarkService().compare([], [])
        with self.assertRaises(ValueError):
            BenchmarkService().compare([0.1, 0.2], [0.05])

    def test_benchmark_name_is_bounded(self):
        result = BenchmarkService().compare(0.1, 0.05, benchmark_name=" X " * 100)
        self.assertLessEqual(len(result["benchmark_name"]), 80)

    def test_benchmark_name_must_be_text(self):
        with self.assertRaises(ValueError):
            BenchmarkService().compare(0.1, 0.05, benchmark_name=None)

    def test_reporting_includes_summary_fields(self):
        report = ReportingService().generate(self.portfolio, report_type="executive", export_format="json")
        self.assertEqual(report["portfolio_name"], "Core")
        self.assertIn("total_return", report)
        self.assertIn("nav", report)

    def test_rebalancing_flags_deviations(self):
        self.portfolio.allocations.create(strategy="alpha", symbol="EURUSD", allocation_percent=70, allocated_capital=7000)
        self.portfolio.allocations.create(strategy="alpha", symbol="XAUUSD", allocation_percent=30, allocated_capital=3000)
        suggestions = RebalancingService().suggestions(self.portfolio, threshold=5)
        self.assertTrue(any(item["action"] in {"rebalance", "buy", "sell"} for item in suggestions))

    def test_attribution_returns_normalized_contributions(self):
        attribution = PerformanceAttributionService().attribute({"equity": 0.05, "macro": 0.03, "fx": -0.01})
        self.assertAlmostEqual(sum(item["contribution"] for item in attribution.values()), 1.0, places=6)
