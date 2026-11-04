from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta

from apps.backtesting.api import BacktestViewSet
from apps.backtesting.models import Backtest, BacktestClusterJob


@override_settings(USE_CELERY=True)
class BacktestQueueReliabilityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='backtest-queue-user', password='test-pass')
        self.backtest = Backtest.objects.create(
            user=self.user,
            strategy='Breakout',
            symbol='R_100',
            timeframe='M1',
            start_date='2026-09-16T18:00:00Z',
            end_date='2026-09-16T19:00:00Z',
            status='pending',
        )
        self.view = BacktestViewSet()

    def test_queue_persists_durable_job_and_publishes_after_backtest_exists(self):
        with patch('apps.backtesting.tasks.execute_backtest.apply_async') as publish:
            self.assertTrue(self.view._queue(self.backtest))

        self.backtest.refresh_from_db()
        job = BacktestClusterJob.objects.get(backtest=self.backtest)
        self.assertEqual(self.backtest.status, 'pending')
        self.assertEqual(job.status, 'pending')
        publish.assert_called_once_with(args=(self.backtest.pk,), retry=False)

    def test_queue_failure_is_recorded_without_leaving_job_running(self):
        with patch('apps.backtesting.tasks.execute_backtest.apply_async', side_effect=RuntimeError('redis unavailable')):
            self.assertFalse(self.view._queue(self.backtest))

        self.backtest.refresh_from_db()
        job = BacktestClusterJob.objects.get(backtest=self.backtest)
        self.assertEqual(self.backtest.status, 'failed')
        self.assertEqual(job.status, 'failed')
        self.assertEqual(self.backtest.result_snapshot['code'], 'BACKTEST_QUEUE_UNAVAILABLE')
        self.assertIn('redis unavailable', self.backtest.result_snapshot['error'])

    def test_recovery_republishes_a_stale_pending_job(self):
        from apps.backtesting.tasks import reconcile_backtest_queue

        job = BacktestClusterJob.objects.create(
            backtest=self.backtest,
            status="pending",
            scheduled_at=timezone.now() - timedelta(minutes=15),
        )
        with patch("apps.backtesting.tasks.execute_backtest.apply_async") as publish:
            result = reconcile_backtest_queue.run(
                limit=10, pending_after_seconds=300, running_after_seconds=3600
            )
        self.assertEqual(result["requeued"], 1)
        publish.assert_called_once_with(args=(self.backtest.pk,), retry=False)
        job.refresh_from_db()
        self.assertGreater(job.scheduled_at, timezone.now() - timedelta(minutes=1))

    def test_recovery_marks_an_abandoned_running_worker_as_failed(self):
        from apps.backtesting.tasks import reconcile_backtest_queue

        self.backtest.status = "running"
        self.backtest.save(update_fields=["status"])
        job = BacktestClusterJob.objects.create(
            backtest=self.backtest,
            status="running",
            locked_at=timezone.now() - timedelta(hours=2),
        )
        result = reconcile_backtest_queue.run(
            limit=10, pending_after_seconds=300, running_after_seconds=3600
        )
        self.backtest.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(result["timed_out"], 1)
        self.assertEqual(self.backtest.status, "failed")
        self.assertEqual(self.backtest.result_snapshot["code"], "BACKTEST_WORKER_TIMEOUT")
        self.assertEqual(job.status, "failed")
        self.assertIsNone(job.locked_at)
