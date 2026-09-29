from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection
from apps.strategies.models import Strategy, StrategyConfiguration, StrategySignal


class Phase3MarketIntelligenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='phase23', password='test-password')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.broker = Broker.objects.create(name='Deriv Phase2/3', broker_type='deriv', status='active')
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id='phase23-account',
            status='active',
            credentials={'account_type': 'demo'},
        )
        BrokerConnection.objects.create(broker=self.broker, broker_account=self.account, status='connected')

    def _strategy(self, name):
        return Strategy.objects.create(name=name, slug=name.lower().replace(' ', '-'), category='Momentum')

    def test_signal_lifecycle_exposes_active_and_expired_states(self):
        active_strategy = self._strategy('Trend')
        expired_strategy = self._strategy('MeanRev')
        active_config = StrategyConfiguration.objects.create(
            strategy=active_strategy, user=self.user, broker_account=self.account, symbol='R_100', timeframe='M1'
        )
        expired_config = StrategyConfiguration.objects.create(
            strategy=expired_strategy, user=self.user, broker_account=self.account, symbol='R_100', timeframe='M1'
        )
        active = StrategySignal.objects.create(strategy=active_strategy, configuration=active_config, symbol='R_100', signal='BUY', confidence=80)
        expired = StrategySignal.objects.create(strategy=expired_strategy, configuration=expired_config, symbol='R_100', signal='SELL', confidence=60)
        StrategySignal.objects.filter(pk=expired.pk).update(timestamp=timezone.now() - timedelta(minutes=10))
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
