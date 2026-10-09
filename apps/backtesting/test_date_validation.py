from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.backtesting.models import Backtest
from apps.backtesting.serializers import BacktestSerializer


class BacktestDateValidationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="backtest-owner", password="test-password")
        self.backtest = Backtest.objects.create(
            user=self.user,
            strategy="Momentum",
            symbol="R_100",
            timeframe="1m",
            start_date=timezone.now() - timedelta(days=2),
            end_date=timezone.now() - timedelta(days=1),
            status="pending",
        )

    def test_update_rejects_future_end_date(self):
        serializer = BacktestSerializer(
            self.backtest,
            data={"end_date": timezone.now() + timedelta(days=1)},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("end_date", serializer.errors)

    def test_update_rejects_reversed_date_range(self):
        serializer = BacktestSerializer(
            self.backtest,
            data={"start_date": timezone.now() - timedelta(hours=1), "end_date": timezone.now() - timedelta(hours=2)},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertTrue(serializer.errors)
