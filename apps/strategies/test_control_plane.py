import json

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from io import StringIO

from apps.brokers.models import Broker, BrokerAccount
from .models import Strategy, StrategyConfiguration


class StrategyControlPlaneTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='strategy-test', password='test-password')
        self.broker = Broker.objects.create(name='Test Broker', broker_type='deriv', status='active')
        self.account = BrokerAccount.objects.create(
            user=self.user, broker=self.broker, account_id='TEST-001', status='active',
            credential_status='ready', credentials={'account_type': 'demo'}, is_preferred=True,
        )
        self.strategy_a = Strategy.objects.create(name='Alpha', slug='alpha', category='Momentum')
        self.strategy_b = Strategy.objects.create(name='Beta', slug='beta', category='Momentum')
        self.config_a = StrategyConfiguration.objects.create(
            strategy=self.strategy_a, user=self.user, broker_account=self.account,
            symbol='R_100', timeframe='M1', criteria={'rsi_min': 30}, is_active=True,
        )
        self.config_b = StrategyConfiguration.objects.create(
            strategy=self.strategy_b, user=self.user, broker_account=self.account,
            symbol='R_100', timeframe='M5', criteria={'rsi_min': 40},
        )

    def test_only_one_current_configuration_is_selected_by_command(self):
        output = StringIO()
        call_command('strategy', 'switch', user=self.user.pk, strategy='beta', stdout=output)
        self.config_a.refresh_from_db()
        self.config_b.refresh_from_db()
        self.assertFalse(self.config_a.is_active)
        self.assertTrue(self.config_b.is_active)
        self.assertIn('SWITCHED CURRENT STRATEGY: beta', output.getvalue())

    def test_criteria_command_updates_json(self):
        call_command('strategy', 'criteria', user=self.user.pk, configuration=self.config_a.pk, criteria=json.dumps({'rsi_min': 35, 'rsi_max': 65}))
        self.config_a.refresh_from_db()
        self.assertEqual(self.config_a.criteria, {'rsi_min': 35, 'rsi_max': 65})
