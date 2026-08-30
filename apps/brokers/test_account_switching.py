from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Broker, BrokerAccount, BrokerConnection

User = get_user_model()


class AccountSwitchingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='account-switch-user', password='test-password')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.broker = Broker.objects.create(
            name='Paper Trading', broker_type='paper', status='active',
            supports_demo=True, supports_live=False, metadata={'auth': 'none'},
        )

    def make_account(self, account_id, preferred=False, connected=True, status='active'):
        account = BrokerAccount.objects.create(
            user=self.user, broker=self.broker, account_id=account_id,
            is_preferred=preferred, status=status, credentials={'account_type': 'demo'},
        )
        if connected:
            BrokerConnection.objects.create(
                broker=self.broker, broker_account=account, status='connected',
                last_ping=timezone.now(), connected_at=timezone.now(),
            )
        return account

    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_switch_changes_the_single_authoritative_active_account(self):
        first = self.make_account('DEMO-1', preferred=True)
        second = self.make_account('DEMO-2')

        result = self.client.post(f'/api/brokers/accounts/{second.pk}/select/', {}, format='json')

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['active_account_id'], second.pk)
        self.assertEqual(result.data['previous_account_id'], first.pk)
        first.refresh_from_db(); second.refresh_from_db()
        self.assertFalse(first.is_preferred)
        self.assertTrue(second.is_preferred)
        self.assertEqual(BrokerAccount.objects.filter(user=self.user, is_preferred=True).count(), 1)

    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_active_endpoint_returns_authoritative_account(self):
        account = self.make_account('DEMO-1', preferred=True)

        result = self.client.get('/api/brokers/accounts/active/')

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['active_account_id'], account.pk)
        self.assertEqual(result.data['active_account']['account_id'], 'DEMO-1')

    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_disconnected_account_cannot_become_active(self):
        current = self.make_account('DEMO-1', preferred=True)
        candidate = self.make_account('DEMO-2', connected=False)

        result = self.client.post(f'/api/brokers/accounts/{candidate.pk}/select/', {}, format='json')

        self.assertEqual(result.status_code, 409)
        self.assertIn('not connected', result.data['detail'])
        current.refresh_from_db(); candidate.refresh_from_db()
        self.assertTrue(current.is_preferred)
        self.assertFalse(candidate.is_preferred)

    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_inactive_account_cannot_become_active(self):
        current = self.make_account('DEMO-1', preferred=True)
        candidate = self.make_account('DEMO-2', status='disabled')

        result = self.client.post(f'/api/brokers/accounts/{candidate.pk}/select/', {}, format='json')

        self.assertEqual(result.status_code, 409)
        self.assertIn('not active', result.data['detail'])
        current.refresh_from_db()
        self.assertTrue(current.is_preferred)

    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_active_account_cannot_be_selected_with_the_wrong_environment(self):
        current = self.make_account('DEMO-1', preferred=True)
        result = self.client.post(
            f'/api/brokers/accounts/{current.pk}/select/',
            {'account_type': 'real'},
            format='json',
        )
        self.assertEqual(result.status_code, 409)
        self.assertIn('not real', result.data['detail'])
        current.refresh_from_db()
        self.assertTrue(current.is_preferred)

    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_second_preferred_account_is_rejected_by_database_invariant(self):
        first = self.make_account('DEMO-1', preferred=True)
        with self.assertRaises(Exception):
            self.make_account('DEMO-2', preferred=True)
        first.refresh_from_db()
        self.assertTrue(first.is_preferred)
        self.assertEqual(BrokerAccount.objects.filter(user=self.user, is_preferred=True).count(), 1)
