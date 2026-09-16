from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.backtesting.serializers import BacktestSerializer, canonical_timeframe


class BacktestSerializerTests(TestCase):
    def test_canonical_timeframe_accepts_ui_aliases(self):
        self.assertEqual(canonical_timeframe('1M'), '1m')
        self.assertEqual(canonical_timeframe('M1'), '1m')
        self.assertEqual(canonical_timeframe('H1'), '1h')
        self.assertEqual(canonical_timeframe('tick'), 'tick')

    def test_serializer_normalizes_one_minute_alias(self):
        now = timezone.now().replace(second=0, microsecond=0)
        serializer = BacktestSerializer(data={
            'strategy': 'Test Strategy',
            'symbol': 'R_100',
            'timeframe': '1M',
            'start_date': now - timedelta(hours=2),
            'end_date': now - timedelta(hours=1),
            'mode': 'candle_close',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['timeframe'], '1m')

    def test_serializer_rejects_future_historical_end(self):
        now = timezone.now().replace(second=0, microsecond=0)
        serializer = BacktestSerializer(data={
            'strategy': 'Test Strategy',
            'symbol': 'R_100',
            'timeframe': '1m',
            'start_date': now,
            'end_date': now + timedelta(hours=1),
            'mode': 'candle_close',
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('end_date', serializer.errors)
