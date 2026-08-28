from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from trading.models.core import Signal


class Phase3MarketIntelligenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='phase23', password='test-password')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_signal_lifecycle_exposes_active_and_expired_states(self):
        from django.utils import timezone
        from datetime import timedelta
        Signal.objects.create(symbol='R_100', direction='BUY', confidence=0.8, strategy='Trend', created_at=timezone.now())
        Signal.objects.create(symbol='R_100', direction='SELL', confidence=0.6, strategy='MeanRev', created_at=timezone.now() - timedelta(minutes=10))
        response = self.client.get('/api/market/signals/lifecycle/?symbol=R_100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)
        self.assertIn(response.data['signals'][0]['lifecycle'], {'active', 'expired'})
        self.assertEqual(response.data['signals'][1]['lifecycle'], 'expired')

    def test_market_intelligence_is_authenticated(self):
        anonymous = APIClient()
        response = anonymous.get('/api/market/intelligence/')
        self.assertIn(response.status_code, {401, 403})
