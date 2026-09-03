import numpy as np
from django.test import SimpleTestCase

from .correlation import CorrelationService
from .diversification import DiversificationService
from .exposure import ExposureService
from .forecasting import ForecastingService
from .optimization import OptimizationService
from .reporting import ReportingService


class PortfolioAnalyticsRealTests(SimpleTestCase):
    def setUp(self):
        rng = np.random.default_rng(42)
        base = rng.normal(0.0005, 0.01, 80)
        self.items = [
            {"symbol": "A", "returns": base + rng.normal(0, 0.003, 80)},
            {"symbol": "B", "returns": base * 0.5 + rng.normal(0.0002, 0.012, 80)},
            {"symbol": "C", "returns": rng.normal(0.0008, 0.008, 80)},
        ]

    def test_optimization_uses_historical_returns(self):
        result = OptimizationService().optimize(self.items, method="min_variance")
        self.assertTrue(result["success"])
        self.assertFalse(result["fallback"])
        self.assertAlmostEqual(sum(result["weights"].values()), 1.0, places=6)
        self.assertGreater(result["observations"], 20)

    def test_optimization_methods_are_not_all_equal_weight(self):
        service = OptimizationService()
        equal = service.optimize(self.items, method="equal_weight")["weights"]
        minimum = service.optimize(self.items, method="min_variance")["weights"]
        self.assertNotEqual(equal, minimum)

    def test_correlation_is_data_driven(self):
        series = {item["symbol"]: item["returns"] for item in self.items}
        result = CorrelationService().matrix(series, method="pearson")
        self.assertAlmostEqual(result["A"]["A"], 1.0, places=6)
        self.assertIsNotNone(result["A"]["B"])
        self.assertNotEqual(result["A"]["B"], 0.0)

    def test_rolling_correlation_requires_real_window(self):
        series = {item["symbol"]: item["returns"] for item in self.items}
        result = CorrelationService().rolling_correlation(series, window=20)
        self.assertEqual(len(result), 61)

    def test_forecast_reports_model_and_observation_count(self):
        result = ForecastingService().forecast(self.items[0]["returns"], method="arima", horizon=7)
        self.assertIn(result["method"], {"arima", "sample_mean"})
        self.assertEqual(result["n_observations"], 80)
        self.assertIsNotNone(result["confidence_level"])

    def test_insufficient_forecast_does_not_fabricate_confidence(self):
        result = ForecastingService().forecast([0.01, -0.01, 0.02], horizon=7)
        self.assertEqual(result["method"], "insufficient_data")
        self.assertIsNone(result["confidence_level"])
        self.assertIsNone(result["forecast"])

    def test_diversification_metrics(self):
        result = DiversificationService().analyze([
            {"symbol": "A", "allocation_percent": 50},
            {"symbol": "B", "allocation_percent": 30},
            {"symbol": "C", "allocation_percent": 20},
        ])
        self.assertAlmostEqual(sum(result["weights"].values()), 1.0, places=6)
        self.assertAlmostEqual(result["herfindahl_index"], 0.38, places=6)
        self.assertEqual(result["effective_positions"], 1 / 0.38)
        self.assertTrue(result["is_concentrated"])

    def test_optimization_respects_weight_bounds(self):
        result = OptimizationService().optimize(self.items, method="min_variance", constraints={"min_weight": 0.2, "max_weight": 0.5})
        self.assertAlmostEqual(sum(result["weights"].values()), 1.0, places=6)
        self.assertTrue(all(0.2 <= weight <= 0.5 for weight in result["weights"].values()))

    def test_exposure_uses_absolute_gross_and_signed_net(self):
        positions = [{"symbol": "A", "notional": -100}, {"symbol": "B", "notional": 40, "direction": "short"}]
        service = ExposureService()
        self.assertEqual(service.gross_exposure(positions), 140.0)
        self.assertEqual(service.net_exposure(positions), 60.0)

    def test_csv_report_contains_persisted_scalar_fields(self):
        report = ReportingService().generate(type("Portfolio", (), {"name": "Research", "net_asset_value": 100, "equity": 100, "current_balance": 100, "initial_balance": 100})(), export_format="csv")
        self.assertIn("metric,value", report["serialized"])
        self.assertIn("portfolio_name,Research", report["serialized"])
