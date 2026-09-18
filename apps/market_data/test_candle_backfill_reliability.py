from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from .models import CandleBackfillRun, MarketSymbol
from .tasks import recover_stale_candle_backfill, run_initial_candle_backfill
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

    def test_stale_queued_initial_run_is_requeued_from_control_page(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="queued",
            count=5000,
            requested_at=timezone.now() - timedelta(minutes=30),
        )
        with patch("apps.market_data.views._celery_state", return_value="PENDING"),              patch("apps.market_data.tasks.run_initial_candle_backfill.delay") as delay:
            delay.return_value.id = "new-task-id"
            recovered = _recover_stale_initial_run(run)

        recovered.refresh_from_db()
        self.assertEqual(recovered.status, "queued")
        self.assertEqual(recovered.task_id, "new-task-id")
        delay.assert_called_once_with(run.pk, count=5000, symbol=None)

    def test_recent_queued_run_is_not_requeued(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="queued",
            count=5000,
        )
        with patch("apps.market_data.views._celery_state") as state:
            recovered = _recover_stale_initial_run(run)
        self.assertEqual(recovered.pk, run.pk)
        state.assert_not_called()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("apps.market_data.tasks.fetch_and_store_all_timeframes")
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

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("apps.market_data.tasks.run_initial_candle_backfill.delay")
    def test_stale_recovery_task_requeues_queued_run(self, delay):
        delay.return_value.id = "recovered-task-id"
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="queued",
            count=5000,
            requested_at=timezone.now() - timedelta(minutes=30),
        )

        result = recover_stale_candle_backfill.apply()

        self.assertEqual(result.state, "SUCCESS")
        run.refresh_from_db()
        self.assertEqual(run.status, "queued")
        self.assertEqual(run.task_id, "recovered-task-id")
