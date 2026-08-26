from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection


class BrokerConnectionActivationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='broker-activation-test')
        self.client.force_login(self.user)
        self.broker = Broker.objects.create(
            name='Deriv',
            broker_type='deriv',
            status='active',
            supports_live=True,
            metadata={'auth': 'oauth'},
        )
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id='CRTEST123',
            access_token='encrypted-test-token',
            token_status='active',
            status='active',
        )

    def test_connect_endpoint_creates_connected_account_state(self):
        connection = BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=self.account,
            status='connected',
        )

        with patch(
            'apps.brokers.views.BrokerConnectionService.connect',
            new=AsyncMock(return_value=connection),
        ):
            response = self.client.post(
                reverse('broker-connect'),
                data={'broker_id': self.broker.id, 'account_id': self.account.id},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['account']['is_connected'])
        self.assertEqual(response.json()['connection']['status'], 'connected')

    def test_connected_state_is_authoritative_in_account_serializer(self):
        self.assertFalse(BrokerConnection.objects.filter(broker_account=self.account, status='connected').exists())
        connection = BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=self.account,
            status='connected',
        )
        self.assertTrue(self.account.connections.filter(status='connected').exists())
        connection.delete()
        self.assertFalse(self.account.connections.filter(status='connected').exists())
