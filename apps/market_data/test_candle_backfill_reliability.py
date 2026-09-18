from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from .models import CandleBackfillRun
from .tasks import reconcile_candle_backfill_runs


class CandleBackfillReliabilityTests(TestCase):
    def test_stale_queued_initial_run_is_republished(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="queued",
            count=5000,
        )
        CandleBackfillRun.objects.filter(pk=run.pk).update(
            requested_at=timezone.now() - timedelta(minutes=10)
        )

        with patch(
            "apps.market_data.tasks.run_initial_candle_backfill.delay"
        ) as delay:
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

        with patch(
            "apps.market_data.tasks.run_initial_candle_backfill.delay"
        ) as delay:
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

        with patch(
            "apps.market_data.tasks.backfill_research_candles.delay"
        ) as delay:
            result = reconcile_candle_backfill_runs(max_age_seconds=300)

        run.refresh_from_db()
        self.assertEqual(result, {"recovered": []})
        self.assertEqual(run.task_id, "active-worker-task")
        delay.assert_not_called()
