from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai_engine.models import Prediction, PredictionOutcome
from apps.brokers.models import Broker, BrokerAccount, Position
from apps.monitoring.services import MonitoringEngine
from apps.strategies.models import Strategy, StrategyConfiguration, StrategyExecution, StrategySignal


class MonitoringSnapshotTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username="monitor-owner", password="test-pass")
        self.other = user_model.objects.create_user(username="monitor-other", password="test-pass")
        self.broker = Broker.objects.create(
            name="Monitoring Deriv", broker_type="deriv", status="active"
        )
        self.owner_account = BrokerAccount.objects.create(
            user=self.owner, broker=self.broker, account_id="MONITOR-OWNER", status="active"
        )
        self.other_account = BrokerAccount.objects.create(
            user=self.other, broker=self.broker, account_id="MONITOR-OTHER", status="active"
        )

    def test_trading_snapshot_is_scoped_to_the_authenticated_accounts(self):
        Position.objects.create(
            broker=self.broker, account=self.owner_account, symbol="R_100",
            status="open",
        )
        Position.objects.create(
            broker=self.broker, account=self.other_account, symbol="R_50",
            status="open",
        )

        owner = MonitoringEngine().trading.snapshot(user=self.owner)
        other = MonitoringEngine().trading.snapshot(user=self.other)

        self.assertEqual(owner["open_positions"], 1)
        self.assertEqual(other["open_positions"], 1)
        self.assertEqual(owner["closed_positions"], 0)
        self.assertEqual(owner["pending_orders"], 0)

    def test_strategy_snapshot_uses_user_configurations_and_execution_records(self):
        strategy = Strategy.objects.create(
            name="Monitoring Trend", slug="monitoring-trend", category="Trend Following"
        )
        configuration = StrategyConfiguration.objects.create(
            strategy=strategy, user=self.owner, symbol="R_100", enabled=True, is_active=True
        )
        StrategyExecution.objects.create(
            strategy=strategy, configuration=configuration, symbol="R_100",
            timeframe="M1", status="failed",
        )
        StrategySignal.objects.create(
            strategy=strategy, configuration=configuration, symbol="R_100", signal="BUY"
        )

        snapshot = MonitoringEngine().strategy.snapshot(user=self.owner)

        self.assertEqual(snapshot["running_strategies"], 1)
        self.assertEqual(snapshot["signals_generated"], 1)
        self.assertEqual(snapshot["strategy_errors"], 1)
        self.assertIsNone(snapshot["win_rate"])

    def test_ai_snapshot_uses_resolved_prediction_outcomes(self):
        prediction = Prediction.objects.create(
            user=self.owner, symbol="R_100", timeframe="M1", prediction="BUY"
        )
        PredictionOutcome.objects.create(prediction=prediction, correct=True)
        Prediction.objects.create(
            user=self.other, symbol="R_50", timeframe="M1", prediction="SELL"
        )

        owner = MonitoringEngine().ai.snapshot(user=self.owner)

        self.assertEqual(owner["predictions_generated"], 1)
        self.assertEqual(owner["prediction_accuracy"], 100.0)

    def test_dashboard_includes_account_scoped_live_counts(self):
        Position.objects.create(
            broker=self.broker, account=self.owner_account, symbol="R_100", status="open"
        )

        dashboard = MonitoringEngine().dashboard(user=self.owner)

        self.assertEqual(dashboard["current_trades"], 1)
        self.assertEqual(dashboard["trading"]["open_positions"], 1)
        self.assertEqual(dashboard["current_predictions"], 0)
        self.assertNotIn("current_cpu_usage", dashboard)
        self.assertNotIn("queue_health", dashboard)

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
    def test_infrastructure_does_not_mistake_local_memory_cache_for_redis(self):
        snapshot = MonitoringEngine().infrastructure.snapshot()
        self.assertEqual(snapshot["redis"], "not_configured")
        self.assertIn(snapshot["database"], {"healthy", "down"})
