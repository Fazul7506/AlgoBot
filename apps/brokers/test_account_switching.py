from unittest.mock import AsyncMock, patch
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken
from .models import Broker, BrokerAccount, BrokerConnection

User = get_user_model()


@override_settings(CREDENTIALS_ENCRYPTION_KEY="test-only-fernet-key")
@patch("core.permissions.has_authorized_broker_connection", new=lambda user, request=None: True)
@patch("core.permissions.has_verified_account_email", new=lambda user, request=None: True)
@patch("core.broker_onboarding.has_authorized_broker_connection", new=lambda user, request=None: True)
@patch("core.broker_onboarding.has_verified_account_email", new=lambda user, request=None: True)
@patch("core.permissions.has_authorized_broker_connection", new=lambda user, request=None: True)
@patch("core.permissions.has_verified_account_email", new=lambda user, request=None: True)
@patch("core.broker_onboarding.has_authorized_broker_connection", new=lambda user, request=None: True)
@patch("core.broker_onboarding.has_verified_account_email", new=lambda user, request=None: True)
@patch("core.permissions.has_authorized_broker_connection", new=lambda user, request=None: True)
@patch("core.permissions.has_verified_account_email", new=lambda user, request=None: True)
class AccountSwitchingTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='account-switch-user', password='test-password')
        self.client = APIClient()
        self.client.force_login(self.user)
        self.broker = Broker.objects.create(
            name='Deriv', broker_type='deriv', status='active',
            supports_demo=True, supports_live=True,
            metadata={'auth': 'oauth', 'avatar_url': 'https://example.com/broker-avatar.png'},
        )
        self.snapshot_sync = AsyncMock(side_effect=self.sync_snapshot)
        self.snapshot_sync_patch = patch('apps.brokers.views.SynchronizationService.sync_account', new=self.snapshot_sync)
        self.snapshot_sync_patch.start()
        self.addCleanup(self.snapshot_sync_patch.stop)

    async def sync_snapshot(self, account):
        account.last_synced_at = timezone.now()
        await sync_to_async(account.save)(update_fields=['last_synced_at'])
        return account, {'account_id': account.account_id, 'account_type': account.account_type, 'balance': str(account.balance)}

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
    def test_credential_ready_disconnected_account_is_connected_and_snapshotted_before_selection(self):
        candidate = self.make_account('DEMO-2', connected=False)
        async def establish_connection(broker, account):
            return await sync_to_async(BrokerConnection.objects.create)(
                broker=broker, broker_account=account, status='connected',
                last_ping=timezone.now(), connected_at=timezone.now(),
            )
        with patch('apps.brokers.views.BrokerConnectionService.connect', new=AsyncMock(side_effect=establish_connection)) as connect:
            result = self.client.post(f'/api/brokers/accounts/{candidate.pk}/select/', {}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['active_account_id'], candidate.pk)
        self.assertTrue(result.data['active_account']['last_synced_at'])
        connect.assert_awaited_once_with(self.broker, candidate)
        self.snapshot_sync.assert_awaited_once_with(candidate)

    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_connection_timeout_keeps_previous_session_account_selected(self):
        previous = self.make_account('DEMO-PREVIOUS', connected=True)
        candidate = self.make_account('REAL-TIMEOUT', account_type='real', connected=False)
        first = self.client.post(f'/api/brokers/accounts/{previous.pk}/select/', {}, format='json')
        self.assertEqual(first.status_code, 200)
        import asyncio
        def timeout_and_close(awaitable, *args, **kwargs):
            close = getattr(awaitable, 'close', None)
            if close:
                close()
            raise asyncio.TimeoutError
        with patch('apps.brokers.views._run_bounded', side_effect=timeout_and_close):
            result = self.client.post(f'/api/brokers/accounts/{candidate.pk}/select/', {}, format='json')
        self.assertEqual(result.status_code, 504)
        active = self.client.get('/api/brokers/accounts/active/')
        self.assertEqual(active.data['active_account_id'], previous.pk)

    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_snapshot_timeout_keeps_previous_account_selected_and_degrades_target(self):
        import asyncio
        previous = self.make_account('DEMO-PREVIOUS', connected=True)
        candidate = self.make_account('REAL-SNAPSHOT-TIMEOUT', account_type='real', connected=True)
        first = self.client.post(f'/api/brokers/accounts/{previous.pk}/select/', {}, format='json')
        self.assertEqual(first.status_code, 200)
        with patch('apps.brokers.views.SynchronizationService.sync_account', new=AsyncMock(side_effect=asyncio.TimeoutError)):
            result = self.client.post(f'/api/brokers/accounts/{candidate.pk}/select/', {}, format='json')
        self.assertEqual(result.status_code, 504)
        self.assertEqual(self.client.get('/api/brokers/accounts/active/').data['active_account_id'], previous.pk)
        candidate.refresh_from_db()
        self.assertEqual(candidate.connections.get().status, 'degraded')

    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_snapshot_timeout_on_current_account_keeps_it_selected_and_connected(self):
        import asyncio
        current = self.make_account('DEMO-CURRENT', connected=True)
        first = self.client.post(f'/api/brokers/accounts/{current.pk}/select/', {}, format='json')
        self.assertEqual(first.status_code, 200)
        with patch('apps.brokers.views.SynchronizationService.sync_account', new=AsyncMock(side_effect=asyncio.TimeoutError)):
            result = self.client.post(f'/api/brokers/accounts/{current.pk}/select/', {}, format='json')
        self.assertEqual(result.status_code, 504)
        self.assertEqual(self.client.get('/api/brokers/accounts/active/').data['active_account_id'], current.pk)
        self.assertEqual(current.connections.get().status, 'connected')

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

        # The browser session and JWT intentionally identify different users.
        # Reject the mixed-identity request before mutating the browser session.
        self.assertEqual(result.status_code, 403)
        self.assertNotIn('active_broker_account_id', client.session)

    def test_jwt_account_list_cannot_clear_a_different_users_browser_session_selection(self):
        from django.test import Client

        self.make_account('JWT-API-ACCOUNT', 'demo')
        other_user = User.objects.create_user(username='other-session-owner', password='test-password')
        other_account = BrokerAccount.objects.create(
            user=other_user, broker=self.broker, account_id='OTHER-SESSION-ACCOUNT',
            status='active', credentials={'account_type': 'real'},
            last_synced_at=timezone.now(),
        )
        other_account.set_access_token('ci-test-token-other-session')
        other_account.save(update_fields=['access_token'])
        BrokerConnection.objects.create(
            broker=self.broker, broker_account=other_account, status='connected',
            last_ping=timezone.now(), connected_at=timezone.now(),
        )

        client = Client()
        self.assertTrue(client.login(username=other_user.username, password='test-password'))
        session = client.session
        session['active_broker_account_id'] = other_account.pk
        session.save()
        token = str(AccessToken.for_user(self.user))

        response = client.get(
            '/api/brokers/accounts/',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(client.session.get('active_broker_account_id'), other_account.pk)

    def test_broker_connect_bearer_jwt_is_not_blocked_by_session_csrf(self):
        account = self.make_account("DEMO-CONNECT-BEARER")
        account.last_synced_at = timezone.now()
        account.save(update_fields=["last_synced_at"])
        connection = account.connections.get()

        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        self.assertTrue(client.login(username=self.user.username, password="test-password"))
        token_response = client.get("/api/auth/browser-token/")
        self.assertEqual(token_response.status_code, 200)
        token = token_response.json()["access"]

        import json
        with patch("apps.brokers.views._verify_user_broker_accounts", new=AsyncMock(
            return_value=([account.pk], [], connection)
        )):
            result = client.post(
                "/api/brokers/connect/",
                data=json.dumps({"broker_id": self.broker.pk, "account_id": account.pk}),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )

        self.assertEqual(result.status_code, 200, getattr(result, "content", b"").decode("utf-8"))
        self.assertEqual(result.json()["active_account_id"], account.pk)

    def test_broker_connect_session_fallback_still_requires_csrf(self):
        account = self.make_account("DEMO-CONNECT-SESSION")
        account.last_synced_at = timezone.now()
        account.save(update_fields=["last_synced_at"])

        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        self.assertTrue(client.login(username=self.user.username, password="test-password"))
        import json
        payload = json.dumps({"broker_id": self.broker.pk, "account_id": account.pk})

        blocked = client.post("/api/brokers/connect/", data=payload, content_type="application/json")
        self.assertEqual(blocked.status_code, 403)

        page = client.get("/trading/")
        self.assertEqual(page.status_code, 200)
        csrf_token = client.cookies["csrftoken"].value
        with patch("apps.brokers.views._verify_user_broker_accounts", new=AsyncMock(
            return_value=([account.pk], [], account.connections.get())
        )):
            accepted = client.post(
                "/api/brokers/connect/",
                data=payload,
                content_type="application/json",
                HTTP_X_CSRFTOKEN=csrf_token,
            )
        self.assertEqual(accepted.status_code, 200, getattr(accepted, "content", b"").decode("utf-8"))
        self.assertEqual(accepted.json()["active_account_id"], account.pk)

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

