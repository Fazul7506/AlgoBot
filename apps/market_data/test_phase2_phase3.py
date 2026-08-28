from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from trading.models.core import Signal


class Phase3MarketIntelligenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='phase23', password='test-password')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_signal_lifecycle_exposes_active_and_expired_states(self):
        active = Signal.objects.create(symbol='R_100', direction='BUY', confidence=0.8, strategy='Trend')
        expired = Signal.objects.create(symbol='R_100', direction='SELL', confidence=0.6, strategy='MeanRev')
        Signal.objects.filter(pk=expired.pk).update(created_at=timezone.now() - timedelta(minutes=10))
        response = self.client.get('/api/market/signals/lifecycle/?symbol=R_100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)
        states = {row['id']: row['lifecycle'] for row in response.data['signals']}
        self.assertEqual(states[active.id], 'active')
        self.assertEqual(states[expired.id], 'expired')

    def test_market_intelligence_is_authenticated(self):
        anonymous = APIClient()
        response = anonymous.get('/api/market/intelligence/')
        self.assertIn(response.status_code, {401, 403})
