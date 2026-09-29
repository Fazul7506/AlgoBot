from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection, Order, Position
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

    def test_signal_lifecycle_reconciles_broker_linked_execution_and_settlement(self):
        strategy = self._strategy('ExecutionLink')
        config = StrategyConfiguration.objects.create(
            strategy=strategy, user=self.user, broker_account=self.account, symbol='R_100', timeframe='M1'
        )
        signal = StrategySignal.objects.create(
            strategy=strategy, configuration=config, symbol='R_100', signal='BUY', confidence=82
        )
        order = Order.objects.create(
            user=self.user, broker=self.broker, account=self.account, strategy=strategy.slug,
            symbol='R_100', direction='buy', order_type='market', contract_type='rise_fall',
            stake='1', status='filled', broker_order_id='BROKER-ORDER-1',
            routing_context={'signal_id': signal.id},
        )
        Position.objects.create(
            broker=self.broker, account=self.account, contract_id='CONTRACT-1',
            transaction_id='TX-1', broker_order_id=order.broker_order_id, symbol='R_100',
            contract_type='CALL', direction='buy', status='settled',
            settlement_time=timezone.now(), closed_at=timezone.now(),
        )
        response = self.client.get('/api/market/signals/lifecycle/?symbol=R_100')
        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.data['signals'] if item['id'] == signal.id)
        self.assertEqual(row['execution_state'], 'executed')
        self.assertEqual(row['settlement_state'], 'settled')
        self.assertEqual(row['contract_id'], 'CONTRACT-1')
        self.assertEqual(row['transaction_id'], 'TX-1')

    def test_market_intelligence_is_authenticated(self):
        anonymous = APIClient()
        response = anonymous.get('/api/market/intelligence/')
        self.assertIn(response.status_code, {401, 403})
