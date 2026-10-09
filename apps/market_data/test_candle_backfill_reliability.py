from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import CandleBackfillEvent, CandleBackfillRun, MarketSymbol
from .tasks import backfill_research_candles, ensure_initial_candle_backfill, ensure_research_candle_backfill, reconcile_candle_backfill_runs, run_initial_candle_backfill


class CandleBackfillReliabilityTests(TestCase):
    def setUp(self):
        self.lock_patcher = patch(
            "apps.market_data.backfill_lock.acquire_backfill_dispatch_lock",
            return_value=MagicMock(),
        )
        self.lock_patcher.start()
        self.addCleanup(self.lock_patcher.stop)
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

    def test_research_backfill_skips_when_another_research_run_is_active(self):
        active = CandleBackfillRun.objects.create(
            scope="research",
            status="running",
            count=250,
            started_at=timezone.now(),
        )
        result = backfill_research_candles.apply(
            kwargs={"count": 250},
        )
        self.assertEqual(result.state, "SUCCESS")
        self.assertEqual(
            result.result,
            {
                "status": "skipped",
                "reason": "research_backfill_active",
                "active_run_id": active.pk,
            },
        )
        self.assertEqual(CandleBackfillRun.objects.filter(scope="research").count(), 1)

    def test_stale_research_runs_are_marked_terminal_by_recovery(self):
        run = CandleBackfillRun.objects.create(
            scope="research",
            status="running",
            count=250,
            started_at=timezone.now() - timedelta(minutes=11),
            last_heartbeat_at=timezone.now() - timedelta(minutes=11),
            task_id="stale-research-task",
        )
        result = reconcile_candle_backfill_runs()
        run.refresh_from_db()
        self.assertEqual(result["recovered"], [])
        self.assertEqual(result["stale_research_failed"], [run.pk])
        self.assertEqual(run.status, "failed")
        self.assertIsNotNone(run.completed_at)
        self.assertIn("heartbeat became stale", run.error)
        self.assertTrue(
            CandleBackfillEvent.objects.filter(
                run=run, event_type="failed", task_id="stale-research-task"
            ).exists()
        )

    def test_unstarted_research_dispatch_is_recovered_after_two_minutes(self):
        run = CandleBackfillRun.objects.create(
            scope="research",
            status="running",
            count=250,
            task_id="never-received-research-task",
            dispatch_at=timezone.now() - timedelta(minutes=3),
        )
        result = reconcile_candle_backfill_runs(max_age_seconds=300)
        run.refresh_from_db()
        self.assertEqual(result["stale_research_failed"], [run.pk])
        self.assertEqual(run.status, "failed")
        self.assertIsNotNone(run.completed_at)
        self.assertIn("heartbeat became stale", run.error)

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
            delay.return_value.id = "ignored-celery-generated-id"
            result = reconcile_candle_backfill_runs(max_age_seconds=300)

        run.refresh_from_db()
        self.assertEqual(result["recovered"][0]["scope"], "initial")
        self.assertEqual(run.status, "running")
        self.assertTrue(run.task_id)
        self.assertEqual(run.task_id, result["recovered"][0]["task_id"])
        self.assertEqual(delay.call_args.kwargs["task_id"], run.task_id)
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

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("apps.market_data.historical.fetch_and_store_all_timeframes")
    def test_timeframe_started_heartbeat_does_not_fake_completion(self, fetch):
        from .tasks import _backfill_timeframe_progress

        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
            result={"work_total": 12, "work_completed": 0},
        )
        _backfill_timeframe_progress("initial", "R_100", "2h", {"status": "started"})
        run.refresh_from_db()
        self.assertEqual(run.result["work_completed"], 0)
        self.assertEqual(run.result["current_timeframe_status"], "started")
        self.assertEqual(run.current_timeframe, "2h")
        self.assertIsNotNone(run.last_heartbeat_at)

        _backfill_timeframe_progress("initial", "R_100", "2h", {"source": "deriv_candles"})
        run.refresh_from_db()
        self.assertEqual(run.result["work_completed"], 1)
        self.assertEqual(run.result["current_timeframe_status"], "completed")

    def test_running_backfill_recovers_after_ten_minutes_without_heartbeat(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
            started_at=timezone.now() - timedelta(minutes=11),
            task_id="stalled-worker-task",
        )
        CandleBackfillRun.objects.filter(pk=run.pk).update(
            last_heartbeat_at=timezone.now() - timedelta(minutes=11),
        )

        with patch("apps.market_data.tasks.run_initial_candle_backfill.apply_async") as publish:
            publish.return_value.id = "ignored-celery-generated-id"
            result = reconcile_candle_backfill_runs(max_age_seconds=300)

        run.refresh_from_db()
        self.assertEqual(result["recovered"][0]["scope"], "initial")
        self.assertEqual(run.status, "running")
        self.assertTrue(run.task_id)
        self.assertIsNone(run.started_at)
        publish.assert_called_once()

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
            publish.return_value.id = "ignored-celery-generated-id"
            result = reconcile_candle_backfill_runs()
        run.refresh_from_db()
        run.refresh_from_db()
        self.assertTrue(run.task_id)
        self.assertEqual(result["recovered"][0]["task_id"], run.task_id)
        self.assertEqual(publish.call_args.kwargs["task_id"], run.task_id)
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
            publish.return_value.id = "ignored-celery-generated-id"
            result = reconcile_candle_backfill_runs()
        run.refresh_from_db()
        self.assertTrue(run.task_id)
        self.assertEqual(result["recovered"][0]["task_id"], run.task_id)
        self.assertEqual(publish.call_args.kwargs["task_id"], run.task_id)
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
            publish.return_value.id = "ignored-celery-generated-id"
            first = reconcile_candle_backfill_runs(max_age_seconds=300)
            run.refresh_from_db()
            self.assertTrue(run.task_id)
            self.assertEqual(first["recovered"][0]["task_id"], run.task_id)
            self.assertEqual(publish.call_args.kwargs["task_id"], run.task_id)

            second = reconcile_candle_backfill_runs(max_age_seconds=300)

        run.refresh_from_db()
        self.assertEqual(run.task_id, first["recovered"][0]["task_id"])
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
    @patch("apps.market_data.tasks.reconcile_candle_backfill_runs")
    def test_automatic_safety_task_does_not_run_recovery_inline(self, reconcile):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
            task_id="active-task",
        )

        result = ensure_initial_candle_backfill(count=5000)

        self.assertEqual(result, {"status": "running", "run_id": run.pk})
        reconcile.assert_not_called()

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
        self.assertEqual(
            publish.call_args.kwargs["task_id"],
            run.task_id,
        )

    def test_all_backfill_delivery_uses_the_dedicated_market_data_queue(self):
        from .tasks import BACKFILL_QUEUE
        self.assertEqual(BACKFILL_QUEUE, "market_data")

    def test_recovery_dispatch_failure_records_authoritative_market_data_queue(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
            task_id="stale-task",
            requested_at=timezone.now() - timedelta(minutes=10),
        )
        CandleBackfillRun.objects.filter(pk=run.pk).update(
            dispatch_at=timezone.now() - timedelta(minutes=10),
            started_at=None,
            accepted_at=None,
            last_heartbeat_at=None,
        )
        with patch(
            "apps.market_data.tasks.run_initial_candle_backfill.apply_async",
            side_effect=RuntimeError("Redis unavailable"),
        ):
            result = reconcile_candle_backfill_runs(max_age_seconds=300)
        run.refresh_from_db()
        self.assertEqual(result.get("recovered"), [])
        self.assertEqual(run.status, "failed")
        event = CandleBackfillEvent.objects.filter(run=run, event_type="error").latest("id")
        self.assertEqual(event.payload.get("queue"), "market_data")

    def test_candle_backfill_task_limits_match_production_contract(self):
        from .tasks import backfill_research_candles, run_initial_candle_backfill
        self.assertEqual(backfill_research_candles.soft_time_limit, 2 * 60 * 60)
        self.assertEqual(run_initial_candle_backfill.soft_time_limit, 4 * 60 * 60)

    def test_research_backfill_scheduler_waits_full_30_minutes_after_completion(self):
        completed_at = timezone.now() - timedelta(minutes=29)
        run = CandleBackfillRun.objects.create(
            scope="research",
            status="completed",
            count=250,
            requested_at=completed_at - timedelta(minutes=5),
            completed_at=completed_at,
        )
        with patch("apps.market_data.tasks.backfill_research_candles.apply_async") as publish:
            result = ensure_research_candle_backfill(count=250)
        self.assertEqual(result["status"], "cooldown")
        self.assertEqual(result["run_id"], run.pk)
        self.assertGreater(result["seconds_remaining"], 0)
        publish.assert_not_called()
        self.assertEqual(CandleBackfillRun.objects.filter(scope="research").count(), 1)

    def test_research_backfill_scheduler_dispatches_after_30_minute_cooldown(self):
        completed_at = timezone.now() - timedelta(minutes=31)
        previous = CandleBackfillRun.objects.create(
            scope="research",
            status="completed",
            count=250,
            requested_at=completed_at - timedelta(minutes=5),
            completed_at=completed_at,
        )
        with patch("apps.market_data.tasks.backfill_research_candles.apply_async") as publish:
            publish.return_value.id = "scheduled-research-task"
            result = ensure_research_candle_backfill(count=250)
        self.assertEqual(result["status"], "dispatched")
        self.assertEqual(result["queue"], "market_data")
        self.assertEqual(CandleBackfillRun.objects.filter(scope="research").count(), 2)
        scheduled = CandleBackfillRun.objects.exclude(pk=previous.pk).get(scope="research")
        self.assertEqual(scheduled.status, "running")
        self.assertEqual(scheduled.task_id, "scheduled-research-task")
        self.assertEqual(publish.call_args.kwargs["args"], (scheduled.pk,))
        self.assertEqual(publish.call_args.kwargs["queue"], "market_data")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("apps.market_data.historical.fetch_and_store_all_timeframes")
    @patch("apps.market_data.tasks.ensure_research_candle_backfill.apply_async")
    def test_research_completion_schedules_next_check_after_30_minutes(self, schedule_next, fetch):
        fetch.return_value = {"symbol": "R_100", "timeframes": {"1m": {"source": "deriv_candles"}}}
        result = backfill_research_candles.apply(kwargs={"count": 250})
        self.assertEqual(result.state, "SUCCESS")
        run = CandleBackfillRun.objects.get(scope="research")
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        schedule_next.assert_called_once()
        self.assertEqual(schedule_next.call_args.kwargs["countdown"], 1800)
        self.assertEqual(schedule_next.call_args.kwargs["queue"], "celery")

    def test_research_backfill_scheduler_is_on_general_worker_queue(self):
        self.assertEqual(
            settings.CELERY_TASK_ROUTES[
                "apps.market_data.tasks.ensure_research_candle_backfill"
            ]["queue"],
            "celery",
        )
        from deriv_platform.celery import app
        entry = app.conf.beat_schedule["research-candle-backfill-completion-relative-scheduler"]
        self.assertEqual(entry["task"], "apps.market_data.tasks.ensure_research_candle_backfill")
        self.assertEqual(entry["schedule"], 60.0)
        self.assertEqual(entry["options"]["queue"], "celery")

    def test_recovery_queue_helper_is_defined_and_canonical(self):
        from .tasks import BACKFILL_QUEUE, _recovery_backfill_queue
        self.assertEqual(_recovery_backfill_queue(1), BACKFILL_QUEUE)
        self.assertEqual(BACKFILL_QUEUE, "market_data")
