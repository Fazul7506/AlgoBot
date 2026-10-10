from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken
from .models import Broker, BrokerAccount, BrokerConnection

User = get_user_model()


class AccountSwitchingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='account-switch-user', password='test-password')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.broker = Broker.objects.create(
            name='Deriv', broker_type='deriv', status='active',
            supports_demo=True, supports_live=True,
            metadata={'auth': 'oauth', 'avatar_url': 'https://example.com/broker-avatar.png'},
        )

    def make_account(self, account_id, account_type='demo', connected=True, status='active'):
        account = BrokerAccount.objects.create(
            user=self.user, broker=self.broker, account_id=account_id,
            status=status, credentials={'account_type': account_type},
        )
        account.set_access_token(f'ci-test-token-{account_id}')
        account.save(update_fields=['access_token'])
        if connected:
            BrokerConnection.objects.create(
                broker=self.broker, broker_account=account, status='connected',
                last_ping=timezone.now(), connected_at=timezone.now(),
            )
        return account

    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_switch_changes_session_active_account(self):
        first = self.make_account('DEMO-1', 'demo')
        second = self.make_account('REAL-2', 'real')
        result = self.client.post(f'/api/brokers/accounts/{second.pk}/select/', {}, format='json')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['active_account_id'], second.pk)
        result = self.client.get('/api/brokers/accounts/active/')
        self.assertEqual(result.data['active_account_id'], second.pk)
        result = self.client.post(f'/api/brokers/accounts/{first.pk}/select/', {}, format='json')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['active_account_id'], first.pk)
        self.assertEqual(self.client.get('/api/brokers/accounts/active/').data['active_account_id'], first.pk)

    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_demo_and_real_accounts_are_equally_selectable(self):
        demo = self.make_account('DEMO-1', 'demo'); real = self.make_account('REAL-1', 'real')
        for account in (demo, real):
            result = self.client.post(f'/api/brokers/accounts/{account.pk}/select/', {}, format='json')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.data['active_account_id'], account.pk)

    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_disconnected_account_cannot_become_active(self):
        candidate = self.make_account('DEMO-2', connected=False)
        result = self.client.post(f'/api/brokers/accounts/{candidate.pk}/select/', {}, format='json')
        self.assertEqual(result.status_code, 409)
        self.assertIn('not connected', result.data['detail'])

    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_inactive_account_cannot_become_active(self):
        candidate = self.make_account('DEMO-2', status='disabled')
        result = self.client.post(f'/api/brokers/accounts/{candidate.pk}/select/', {}, format='json')
        self.assertEqual(result.status_code, 409)
        self.assertIn('not active', result.data['detail'])

    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_wrong_environment_is_rejected_by_broker_verified_type(self):
        demo = self.make_account('DEMO-1', 'demo')
        result = self.client.post(
            f'/api/brokers/accounts/{demo.pk}/select/', {'account_type': 'real'}, format='json'
        )
        self.assertEqual(result.status_code, 409)
        self.assertIn('not real', result.data['detail'])


    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_jwt_for_another_user_cannot_write_to_browser_session_account_selection(self):
        account = self.make_account('DEMO-CROSS-USER', 'demo')
        other_user = User.objects.create_user(username='different-browser-session', password='test-password')
        client = __import__('django.test', fromlist=['Client']).Client(enforce_csrf_checks=True)
        self.assertTrue(client.login(username=other_user.username, password='test-password'))
        page = client.get('/trading/')
        self.assertEqual(page.status_code, 200)
        csrf_token = client.cookies['csrftoken'].value
        token = str(AccessToken.for_user(self.user))

        result = client.post(
            f'/api/brokers/accounts/{account.pk}/select/',
            {},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(result.status_code, 403)
        self.assertIn('different users', result.json()['detail'])
        self.assertNotIn('active_broker_account_id', client.session)

    def test_session_authenticated_switch_requires_csrf_token(self):
        self.make_account('DEMO-CSRF-1', 'demo')
        second = self.make_account('REAL-CSRF-2', 'real')
        client = __import__('django.test', fromlist=['Client']).Client(enforce_csrf_checks=True)
        self.assertTrue(client.login(username='account-switch-user', password='test-password'))
        result = client.post(f'/api/brokers/accounts/{second.pk}/select/', {}, content_type='application/json')
        self.assertEqual(result.status_code, 403)

    def test_browser_jwt_switch_does_not_require_csrf_token(self):
        self.make_account('DEMO-JWT-1', 'demo')
        second = self.make_account('REAL-JWT-2', 'real')
        client = __import__('django.test', fromlist=['Client']).Client(enforce_csrf_checks=True)
        self.assertTrue(client.login(username='account-switch-user', password='test-password'))
        token_response = client.get('/api/auth/browser-token/')
        self.assertEqual(token_response.status_code, 200)
        token = token_response.json()['access']
        result = client.post(
            f'/api/brokers/accounts/{second.pk}/select/',
            {},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['active_account_id'], second.pk)

    def test_session_authenticated_switch_accepts_current_csrf_token(self):
        self.make_account('DEMO-CSRF-1', 'demo')
        second = self.make_account('REAL-CSRF-2', 'real')
        client = __import__('django.test', fromlist=['Client']).Client(enforce_csrf_checks=True)
        self.assertTrue(client.login(username='account-switch-user', password='test-password'))
        page = client.get('/trading/')
        self.assertEqual(page.status_code, 200)
        csrf_token = client.cookies['csrftoken'].value

        result = client.post(
            f'/api/brokers/accounts/{second.pk}/select/',
            {},
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['active_account_id'], second.pk)

