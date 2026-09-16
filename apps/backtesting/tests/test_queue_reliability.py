from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

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
