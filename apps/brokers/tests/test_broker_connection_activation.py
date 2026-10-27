from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from asgiref.sync import async_to_sync

from apps.brokers.exceptions import BrokerAuthenticationError, BrokerConnectionError
from apps.brokers.services import BrokerConnectionService
from apps.brokers.models import Broker, BrokerAccount, BrokerConnection


@override_settings(CREDENTIALS_ENCRYPTION_KEY="test-only-fernet-key")
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


    def _verify_selected_account(self, account_id, account_type, is_virtual):
        self.account.account_id = account_id
        self.account.credentials = {"account_type": account_type}
        self.account.save(update_fields=["account_id", "credentials"])
        adapter = type("AdapterStub", (), {})()
        adapter.connect = AsyncMock(return_value={
            "account_id": account_id,
            "is_virtual": is_virtual,
            "balance": 125.50,
            "currency": "USD",
        })
        adapter.ping = AsyncMock(return_value=12.5)
        with patch("apps.brokers.services.BrokerRegistry.adapter", return_value=adapter):
            connection = async_to_sync(BrokerConnectionService().connect)(self.broker, self.account)
        self.account.refresh_from_db()
        self.assertEqual(connection.status, "connected")
        self.assertEqual(self.account.credentials["account_type"], account_type)
        self.assertEqual(self.account.credentials["connection_health"], "verified")
        self.assertEqual(str(self.account.balance), "125.50000000")
        return connection

    def test_demo_account_connects_and_is_verified(self):
        self._verify_selected_account("VRTC123456", "demo", True)

    def test_real_account_connects_and_is_verified(self):
        self._verify_selected_account("CR123456", "real", False)

    def test_connection_rejects_provider_account_id_mismatch_without_rewriting_selection(self):
        self.account.credentials = {"account_type": "demo"}
        self.account.save(update_fields=["credentials"])
        adapter = type("AdapterStub", (), {})()
        adapter.connect = AsyncMock(return_value={
            "account_id": "CR999999",
            "is_virtual": False,
            "balance": 500,
            "currency": "USD",
        })
        adapter.ping = AsyncMock(return_value=10)
        with patch("apps.brokers.services.BrokerRegistry.adapter", return_value=adapter):
            with self.assertRaises(BrokerAuthenticationError):
                async_to_sync(BrokerConnectionService().connect)(self.broker, self.account)
        self.account.refresh_from_db()
        self.assertEqual(self.account.account_id, "CRTEST123")
        self.assertFalse(BrokerConnection.objects.filter(broker_account=self.account, status="connected").exists())

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