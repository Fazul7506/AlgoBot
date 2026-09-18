from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from .models import CandleBackfillRun, MarketSymbol
from .tasks import reconcile_candle_backfill_runs, run_initial_candle_backfill
from .views import _recover_stale_initial_run


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

    def test_stale_queued_initial_run_is_republished(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="queued",
            count=5000,
        )
        CandleBackfillRun.objects.filter(pk=run.pk).update(
            requested_at=timezone.now() - timedelta(minutes=10)
        )

        with patch("apps.market_data.tasks.run_initial_candle_backfill.delay") as delay:
            delay.return_value.id = "recovered-task-id"
            result = reconcile_candle_backfill_runs(max_age_seconds=300)

        run.refresh_from_db()
        self.assertEqual(result["recovered"][0]["scope"], "initial")
        self.assertEqual(run.status, "queued")
        self.assertEqual(run.task_id, "recovered-task-id")
        self.assertEqual(delay.call_count, 1)

    def test_recent_queued_run_is_not_republished(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="queued",
            count=5000,
        )

        with patch("apps.market_data.tasks.run_initial_candle_backfill.delay") as delay:
            result = reconcile_candle_backfill_runs(max_age_seconds=300)

        run.refresh_from_db()
        self.assertEqual(result, {"recovered": []})
        self.assertEqual(run.task_id, "")
        delay.assert_not_called()

    def test_running_run_is_never_duplicated(self):
        run = CandleBackfillRun.objects.create(
            scope="research",
            status="running",
            count=250,
            started_at=timezone.now() - timedelta(minutes=20),
            task_id="active-worker-task",
        )
        CandleBackfillRun.objects.filter(pk=run.pk).update(
            requested_at=timezone.now() - timedelta(minutes=20)
        )

        with patch("apps.market_data.tasks.backfill_research_candles.delay") as delay:
            result = reconcile_candle_backfill_runs(max_age_seconds=300)

        run.refresh_from_db()
        self.assertEqual(result, {"recovered": []})
        self.assertEqual(run.task_id, "active-worker-task")
        delay.assert_not_called()

    def test_stale_running_initial_run_is_republished(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
            started_at=timezone.now() - timedelta(minutes=61),
            task_id="lost-worker-task",
        )

        with patch("apps.market_data.tasks.run_initial_candle_backfill.delay") as delay:
            delay.return_value.id = "recovered-task-id"
            result = reconcile_candle_backfill_runs(max_age_seconds=300)

        run.refresh_from_db()
        self.assertEqual(result["recovered"][0]["scope"], "initial")
        self.assertEqual(run.status, "queued")
        self.assertEqual(run.task_id, "recovered-task-id")
        delay.assert_called_once()

    def test_control_page_requeues_stale_initial_delivery(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="queued",
            count=5000,
        )
        CandleBackfillRun.objects.filter(pk=run.pk).update(
            requested_at=timezone.now() - timedelta(minutes=30)
        )
        run.refresh_from_db()

        with patch("apps.market_data.views._celery_state", return_value="PENDING"), patch(
            "apps.market_data.tasks.run_initial_candle_backfill.delay"
        ) as delay:
            delay.return_value.id = "new-task-id"
            recovered = _recover_stale_initial_run(run)

        recovered.refresh_from_db()
        self.assertEqual(recovered.status, "queued")
        self.assertEqual(recovered.task_id, "new-task-id")
        self.assertEqual(delay.call_count, 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("apps.market_data.historical.fetch_and_store_all_timeframes")
    def test_initial_backfill_marks_success_after_real_ingestion_call(self, fetch):
        fetch.return_value = {
            "symbol": "R_100",
            "timeframes": {"1m": {"source": "deriv_candles"}},
        }
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="queued",
            count=5000,
        )

        result = run_initial_candle_backfill.apply(
            args=(run.pk,),
            kwargs={"count": 5000},
        )

        self.assertEqual(result.state, "SUCCESS")
        run.refresh_from_db()
        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.result["symbols_completed"], 1)
        fetch.assert_called_once()
