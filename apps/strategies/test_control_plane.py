import json

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from io import StringIO
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.brokers.models import Broker, BrokerAccount
from .models import Strategy, StrategyConfiguration
from .views import StrategyViewSet


class StrategyControlPlaneTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='strategy-test', password='test-password')
        self.broker = Broker.objects.create(name='Test Broker', broker_type='deriv', status='active')
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id='TEST-001',
            status='active',
            credentials={'account_type': 'demo'},
        )
        self.strategy_a = Strategy.objects.create(name='Alpha', slug='alpha', category='Momentum')
        self.strategy_b = Strategy.objects.create(name='Beta', slug='beta', category='Momentum')
        self.config_a = StrategyConfiguration.objects.create(
            strategy=self.strategy_a,
            user=self.user,
            broker_account=self.account,
            symbol='R_100',
            timeframe='M1',
            criteria={'rsi_min': 30},
            is_active=True,
        )
        self.config_b = StrategyConfiguration.objects.create(
            strategy=self.strategy_b,
            user=self.user,
            broker_account=self.account,
            symbol='R_100',
            timeframe='M5',
            criteria={'rsi_min': 40},
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
        call_command(
            'strategy',
            'criteria',
            user=self.user.pk,
            configuration=self.config_a.pk,
            criteria=json.dumps({'rsi_min': 35, 'rsi_max': 65}),
        )
        self.config_a.refresh_from_db()
        self.assertEqual(self.config_a.criteria, {'rsi_min': 35, 'rsi_max': 65})

    def test_available_reports_configured_and_running_states(self):
        request = APIRequestFactory().get('/api/strategies/available/')
        force_authenticate(request, user=self.user)
        response = StrategyViewSet.as_view({'get': 'available'})(request)
        self.assertEqual(response.status_code, 200)
        payload = response.data
        self.assertEqual(payload['configured_count'], 2)
        self.assertEqual(payload['running_count'], 1)
        alpha = next(item for item in payload['strategies'] if item['slug'] == 'alpha')
        beta = next(item for item in payload['strategies'] if item['slug'] == 'beta')
        self.assertTrue(alpha['configured'])
        self.assertTrue(alpha['running'])
        self.assertTrue(beta['configured'])
        self.assertFalse(beta['running'])

    def test_disconnect_preserves_configuration_and_clears_running_state(self):
        request = APIRequestFactory().post(
            f'/api/strategies/{self.strategy_a.pk}/disconnect/',
            {'configuration_id': self.config_a.pk},
            format='json',
        )
        force_authenticate(request, user=self.user)
        response = StrategyViewSet.as_view({'post': 'disconnect'})(request, pk=self.strategy_a.pk)
        self.assertEqual(response.status_code, 200)
        self.config_a.refresh_from_db()
        self.assertFalse(self.config_a.is_active)
        self.assertTrue(self.config_a.enabled)
        self.assertEqual(self.config_a.symbol, 'R_100')

    def test_switch_moves_running_state_to_another_configuration(self):
        request = APIRequestFactory().post(
            f'/api/strategies/{self.strategy_b.pk}/switch/',
            {'configuration_id': self.config_b.pk},
            format='json',
        )
        force_authenticate(request, user=self.user)
        response = StrategyViewSet.as_view({'post': 'switch'})(request, pk=self.strategy_b.pk)
        self.assertEqual(response.status_code, 200)
        self.config_a.refresh_from_db()
        self.config_b.refresh_from_db()
        self.assertFalse(self.config_a.is_active)
        self.assertTrue(self.config_b.is_active)
