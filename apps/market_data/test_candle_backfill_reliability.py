from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from .models import CandleBackfillEvent, CandleBackfillRun, MarketSymbol
from .tasks import reconcile_candle_backfill_runs, run_initial_candle_backfill


class CandleBackfillReliabilityTests(TestCase):
    def setUp(self):
        self.symbol = MarketSymbol.objects.create(
            symbol="R_100",
            display_name="Volatility 100",
            market="Volatility Indices",
            broker="deriv",
            is_active=True,
            is_tradable=True,
        )

    def test_status_choices_exclude_queued(self):
        self.assertEqual(
            [value for value, _ in CandleBackfillRun.STATUS_CHOICES],
            ["running", "completed", "failed"],
        )
        run = CandleBackfillRun.objects.create(scope="initial", count=5000)
        self.assertEqual(run.status, "running")

    def test_stale_running_initial_run_is_republished_without_queue_state(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
            started_at=timezone.now() - timedelta(minutes=61),
            task_id="lost-worker-task",
        )

        with patch("apps.market_data.tasks.run_initial_candle_backfill.apply_async") as delay:
            delay.return_value.id = "recovered-task-id"
            result = reconcile_candle_backfill_runs(max_age_seconds=300)

        run.refresh_from_db()
        self.assertEqual(result["recovered"][0]["scope"], "initial")
        self.assertEqual(run.status, "running")
        self.assertEqual(run.task_id, "recovered-task-id")
        delay.assert_called_once()

    def test_recent_running_run_is_not_republished(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
            started_at=timezone.now(),
            task_id="active-worker-task",
        )

        with patch("apps.market_data.tasks.run_initial_candle_backfill.delay") as delay:
            result = reconcile_candle_backfill_runs(max_age_seconds=300)

        run.refresh_from_db()
        self.assertEqual(result, {"recovered": []})
        self.assertEqual(run.status, "running")
        delay.assert_not_called()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("apps.market_data.historical.fetch_and_store_all_timeframes")
    def test_initial_backfill_marks_success_after_real_ingestion_call(self, fetch):
        fetch.return_value = {
            "symbol": "R_100",
            "timeframes": {"1m": {"source": "deriv_candles"}},
        }
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
        )

        result = run_initial_candle_backfill.apply(
            args=(run.pk,),
            kwargs={"count": 5000},
        )

        self.assertEqual(result.state, "SUCCESS")
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.result["symbols_completed"], 1)
        fetch.assert_called_once()
        self.assertGreater(CandleBackfillEvent.objects.filter(run=run).count(), 0)
        self.assertIsNotNone(run.last_heartbeat_at)


    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("apps.market_data.historical.fetch_and_store_all_timeframes")
    def test_initial_backfill_fails_when_any_broker_timeframe_fails(self, fetch):
        fetch.return_value = {
            "symbol": "R_100",
            "timeframes": {
                "1m": {"source": "deriv_candles"},
                "5m": {"status": "failed", "error": "Deriv timeout"},
            },
        }
        run = CandleBackfillRun.objects.create(scope="initial", status="running", count=5000)
        result = run_initial_candle_backfill.apply(args=(run.pk,), kwargs={"count": 5000})
        self.assertEqual(result.state, "FAILURE")
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.result["symbols_failed"], 1)
        self.assertEqual(run.result["percent"], 100.0)
        self.assertIn("R_100", run.error)

    def test_unconfirmed_dispatch_is_republished_and_started_at_is_not_fabricated(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
            started_at=None,
            task_id="undelivered-task",
        )
        CandleBackfillRun.objects.filter(pk=run.pk).update(
            requested_at=timezone.now() - timedelta(minutes=3),
        )
        with patch("apps.market_data.tasks.run_initial_candle_backfill.apply_async") as publish:
            publish.return_value.id = "recovered-task-id"
            result = reconcile_candle_backfill_runs()
        run.refresh_from_db()
        self.assertEqual(result["recovered"][0]["task_id"], "recovered-task-id")
        self.assertEqual(run.task_id, "recovered-task-id")
        self.assertIsNone(run.started_at)
        self.assertTrue(
            CandleBackfillEvent.objects.filter(run=run, event_type="recovered").exists()
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("apps.market_data.historical.fetch_and_store_all_timeframes")
    def test_partial_timeframe_failure_is_terminal_and_logged(self, fetch):
        fetch.return_value = {
            "symbol": "R_100",
            "timeframes": {
                "1m": {"source": "deriv_candles"},
                "5m": {"status": "failed", "error": "Deriv timeout"},
            },
        }
        run = CandleBackfillRun.objects.create(scope="initial", status="running", count=5000)
        result = run_initial_candle_backfill.apply(args=(run.pk,), kwargs={"count": 5000})
        run.refresh_from_db()
        self.assertEqual(result.state, "FAILURE")
        self.assertEqual(run.status, "failed")
        self.assertTrue(
            CandleBackfillEvent.objects.filter(run=run, event_type="failed").exists()
        )
