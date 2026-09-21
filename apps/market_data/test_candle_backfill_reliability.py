from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import CandleBackfillEvent, CandleBackfillRun, MarketSymbol
from .tasks import ensure_initial_candle_backfill, reconcile_candle_backfill_runs, run_initial_candle_backfill


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

    def test_active_symbol_scope_is_deriv_only(self):
        MarketSymbol.objects.create(
            symbol="OTHER_100",
            display_name="Other Broker 100",
            market="Volatility Indices",
            broker="other",
            is_active=True,
            is_tradable=True,
        )
        from .tasks import _active_symbols
        self.assertEqual(_active_symbols(), ["R_100"])

    def test_recovery_runs_on_general_worker_queue(self):
        self.assertEqual(
            settings.CELERY_TASK_ROUTES[
                "apps.market_data.tasks.reconcile_candle_backfill_runs"
            ]["queue"],
            "celery",
        )

    def test_execution_duration_is_not_request_age(self):
        requested = timezone.now() - timedelta(hours=2)
        started = requested + timedelta(hours=1, minutes=30)
        completed = started + timedelta(minutes=5)
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="completed",
            started_at=started,
            completed_at=completed,
        )
        CandleBackfillRun.objects.filter(pk=run.pk).update(requested_at=requested)
        run.refresh_from_db()
        from .views import _run_payload

        payload = _run_payload(run)
        self.assertEqual(payload["duration_seconds"], 5 * 60)
        self.assertFalse(payload["live"])
        self.assertEqual(payload["worker_state"], "COMPLETED")

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

        with patch("apps.market_data.tasks.run_initial_candle_backfill.apply_async") as delay:
            result = reconcile_candle_backfill_runs(max_age_seconds=300)

        run.refresh_from_db()
        self.assertEqual(result, {"recovered": []})
        self.assertEqual(run.status, "running")
        delay.assert_not_called()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("apps.market_data.historical.fetch_and_store_all_timeframes")
    def test_initial_backfill_marks_success_after_real_ingestion_call(self, fetch):
        def ingest(symbol, count, request_interval, progress_callback):
            payload = {
                "symbol": symbol,
                "timeframes": {},
            }
            for timeframe in (
                "1m", "2m", "5m", "10m", "15m", "30m",
                "1h", "2h", "4h", "8h", "1d",
            ):
                value = {"source": "deriv_candles"}
                payload["timeframes"][timeframe] = value
                progress_callback(timeframe, value)
            tick_value = {"received": 5000, "valid": 5000}
            payload["timeframes"]["tick-derived"] = tick_value
            progress_callback("tick-derived", tick_value)
            return payload

        fetch.side_effect = ingest
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
        self.assertEqual(run.result["work_completed"], 12)
        self.assertEqual(run.result["work_total"], 12)
        self.assertEqual(run.result["work_percent"], 100.0)
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

    def test_worker_received_signal_persists_acceptance_before_task_start(self):
        from .tasks import _record_candle_backfill_worker_received

        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
            task_id="received-task",
        )
        request = type(
            "Request",
            (),
            {
                "task": "apps.market_data.tasks.run_initial_candle_backfill",
                "id": "received-task",
                "args": [run.pk],
            },
        )()
        _record_candle_backfill_worker_received(request=request)

        run.refresh_from_db()
        self.assertIsNotNone(run.accepted_at)
        self.assertIsNotNone(run.last_heartbeat_at)
        self.assertIsNone(run.started_at)
        self.assertTrue(run.worker_hostname)
        self.assertTrue(
            CandleBackfillEvent.objects.filter(
                run=run, event_type="worker_received", task_id="received-task"
            ).exists()
        )

    def test_received_but_not_started_run_is_recovered_after_five_minutes(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
            task_id="received-task",
            accepted_at=timezone.now() - timedelta(minutes=6),
        )
        with patch("apps.market_data.tasks.run_initial_candle_backfill.apply_async") as publish:
            publish.return_value.id = "recovered-received-task"
            result = reconcile_candle_backfill_runs()
        run.refresh_from_db()
        self.assertEqual(result["recovered"][0]["task_id"], "recovered-received-task")
        self.assertIsNone(run.started_at)
        publish.assert_called_once()

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

    def test_recovery_cooldown_prevents_rapid_republish_of_same_dispatch(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
            task_id="first-dispatch",
        )
        CandleBackfillRun.objects.filter(pk=run.pk).update(
            requested_at=timezone.now() - timedelta(minutes=6),
            dispatch_at=timezone.now() - timedelta(minutes=6),
        )

        with patch("apps.market_data.tasks.run_initial_candle_backfill.apply_async") as publish:
            publish.return_value.id = "recovered-once"
            first = reconcile_candle_backfill_runs(max_age_seconds=300)
            self.assertEqual(first["recovered"][0]["task_id"], "recovered-once")

            second = reconcile_candle_backfill_runs(max_age_seconds=300)

        run.refresh_from_db()
        self.assertEqual(run.task_id, "recovered-once")
        self.assertEqual(second, {"recovered": []})
        publish.assert_called_once()

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


    def test_unknown_task_delivery_fails_only_matching_run(self):
        from .tasks import _record_candle_backfill_unknown_task

        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
            task_id="unknown-task",
        )
        _record_candle_backfill_unknown_task(
            name="apps.market_data.tasks.run_initial_candle_backfill",
            id="unknown-task",
        )
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertIn("does not have the current task registered", run.error)
        self.assertTrue(
            CandleBackfillEvent.objects.filter(
                run=run, event_type="error", task_id="unknown-task"
            ).exists()
        )

    def test_unknown_other_task_does_not_change_backfill_run(self):
        from .tasks import _record_candle_backfill_unknown_task

        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
            task_id="other-task",
        )
        _record_candle_backfill_unknown_task(
            name="apps.other.tasks.some_task",
            id="other-task",
        )
        run.refresh_from_db()
        self.assertEqual(run.status, "running")


    def test_initial_backfill_is_automatically_scheduled_on_celery(self):
        self.assertEqual(
            settings.CELERY_TASK_ROUTES[
                "apps.market_data.tasks.ensure_initial_candle_backfill"
            ]["queue"],
            "celery",
        )
        from deriv_platform.celery import app
        entry = app.conf.beat_schedule["initial-candle-backfill-automatic-every-5-minutes"]
        self.assertEqual(entry["task"], "apps.market_data.tasks.ensure_initial_candle_backfill")
        self.assertEqual(entry["options"]["queue"], "celery")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_automatic_initial_dispatch_marks_trigger_automatic(self):
        with patch("apps.market_data.tasks.run_initial_candle_backfill.apply_async") as publish:
            publish.return_value.id = "automatic-task-id"
            result = ensure_initial_candle_backfill(count=5000)
        self.assertEqual(result["status"], "dispatched")
        run = CandleBackfillRun.objects.get(scope="initial")
        self.assertEqual(run.status, "running")
        self.assertEqual((run.result or {}).get("trigger"), "automatic")
        self.assertEqual((run.result or {}).get("automatic_attempts"), 1)
        self.assertEqual(result["queue"], "market_data")
        publish.assert_called_once()

    def test_recovery_alternates_to_general_celery_queue(self):
        from .tasks import _recovery_backfill_queue
        self.assertEqual(_recovery_backfill_queue(0), "market_data")
        self.assertEqual(_recovery_backfill_queue(1), "celery")
        self.assertEqual(_recovery_backfill_queue(2), "market_data")
