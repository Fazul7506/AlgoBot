from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.brokers.exceptions import BrokerConnectionError
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
            token_status='active',
            status='active',
        )
        self.account.set_access_token('test-token')
        self.account.save(update_fields=['access_token'])

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
                HTTP_ORIGIN='http://testserver',
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['account']['is_connected'])
        self.assertEqual(response.json()['connection']['status'], 'connected')

    def test_primary_connection_is_not_failed_by_secondary_account_error(self):
        secondary = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id='CRSECONDARY123',
            token_status='active',
            status='active',
        )
        secondary.set_access_token('test-token')
        secondary.save(update_fields=['access_token'])
        primary_connection = BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=self.account,
            status='connected',
        )

        with patch(
            'apps.brokers.views.BrokerConnectionService.connect',
            new=AsyncMock(side_effect=[primary_connection, BrokerConnectionError('secondary account unavailable')]),
        ):
            response = self.client.post(
                reverse('broker-connect'),
                data={'broker_id': self.broker.id, 'account_id': self.account.id},
                HTTP_ORIGIN='http://testserver',
            )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['account']['is_connected'])
        self.assertTrue(payload['partial_connection'])
        self.assertFalse(payload['all_accounts_ready'])
        self.assertEqual(payload['connected_account_ids'], [self.account.id])
        self.assertEqual(payload['failed_accounts'][0]['account_id'], secondary.account_id)

    def test_connected_state_is_authoritative_in_account_model(self):
        self.assertFalse(BrokerConnection.objects.filter(broker_account=self.account, status='connected').exists())
        connection = BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=self.account,
            status='connected',
        )
        self.assertTrue(self.account.connections.filter(status='connected').exists())
        connection.delete()
        self.assertFalse(self.account.connections.filter(status='connected').exists())