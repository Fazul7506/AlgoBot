from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import Strategy, StrategyConfiguration
from .services import StrategyService


class StrategyBuilderApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='builder-test', password='test-password')
        self.client.force_authenticate(user=self.user)
        StrategyService().sync_catalog()
        self.strategy = Strategy.objects.filter(enabled=True).order_by('id').first()

    def test_available_returns_authoritative_catalog(self):
        response = self.client.get('/api/strategies/available/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['strategies'])
        self.assertIn('configured', response.data['strategies'][0])

    def test_validate_config_rejects_bad_json_shape(self):
        response = self.client.post(
            f'/api/strategies/{self.strategy.pk}/validate_config/',
            {'symbol': 'R_75', 'timeframe': 'M1', 'parameters': ['not', 'an', 'object']},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['status'], 'invalid')

    def test_validate_config_accepts_research_configuration(self):
        response = self.client.post(
            f'/api/strategies/{self.strategy.pk}/validate_config/',
            {'symbol': 'R_75', 'timeframe': 'M5', 'parameters': {}},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'valid')
        self.assertFalse(response.data['ready_for_live_trade'])

    def test_configure_is_user_scoped_and_does_not_execute(self):
        response = self.client.post(
            f'/api/strategies/{self.strategy.pk}/configure/',
            {
                'symbol': 'R_75',
                'timeframe': 'M15',
                'parameters': {'lookback': 20},
                'risk_profile': 'balanced',
                'schedule': 'manual',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        configuration = StrategyConfiguration.objects.get(user=self.user, strategy=self.strategy, symbol='R_75', timeframe='M15')
        self.assertEqual(configuration.parameters, {'lookback': 20})
        self.assertFalse(configuration.broker_account_id is not None)
