from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.contrib.sessions.middleware import SessionMiddleware

from core.account_context import SESSION_KEY, get_active_account, select_account
from apps.brokers.models import Broker, BrokerAccount, BrokerConnection
from apps.brokers.serializers import BrokerAccountSerializer
from django.utils import timezone


@override_settings(CREDENTIALS_ENCRYPTION_KEY="test-only-fernet-key")
class AccountSwitchingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='account-switch-user',
            password='test-password',
        )
        self.broker = Broker.objects.create(
            name='Deriv Switching Test',
            broker_type='deriv',
            status='active',
            supports_live=False,
            metadata={'auth': 'oauth'},
        )
        self.account_one = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id='DEMO-ONE',
            credentials={'account_type': 'demo'},
        )
        self.account_two = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id='DEMO-TWO',
            credentials={'account_type': 'demo'},
        )
        self.account_one.set_access_token('ci-test-token-one')
        self.account_two.set_access_token('ci-test-token-two')
        self.account_one.save(update_fields=['access_token'])
        self.account_two.save(update_fields=['access_token'])
        BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=self.account_one,
            status='connected',
        )
        BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=self.account_two,
            status='connected',
        )

    def _request(self, path='/api/brokers/accounts/active/'):
        request = RequestFactory().get(path)
        SessionMiddleware(lambda _request: None).process_request(request)
        request.session.save()
        request.user = self.user
        return request

    def test_selection_is_session_scoped_and_switches_accounts(self):
        request = self._request()
        self.account_one.last_synced_at = timezone.now()
        self.account_one.save(update_fields=['last_synced_at'])
        self.account_two.last_synced_at = timezone.now()
        self.account_two.save(update_fields=['last_synced_at'])

        select_account(request, self.account_one)
        self.assertEqual(request.session[SESSION_KEY], self.account_one.pk)
        self.assertEqual(get_active_account(self.user, request=request), self.account_one)

        select_account(request, self.account_two)
        self.assertEqual(request.session[SESSION_KEY], self.account_two.pk)
        self.assertEqual(get_active_account(self.user, request=request), self.account_two)

    def test_query_parameter_cannot_override_session_active_account(self):
        request = self._request(
            f'/api/brokers/accounts/active/?account_id={self.account_two.pk}'
        )
        self.account_one.last_synced_at = timezone.now()
        self.account_one.save(update_fields=['last_synced_at'])
        select_account(request, self.account_one)
        self.assertEqual(get_active_account(self.user, request=request), self.account_one)

    def test_request_header_cannot_override_session_active_account(self):
        request = self._request()
        self.account_one.last_synced_at = timezone.now()
        self.account_one.save(update_fields=['last_synced_at'])
        select_account(request, self.account_one)
        request.META["HTTP_X_ALGOBOT_ACCOUNT_ID"] = str(self.account_two.pk)

        self.assertEqual(get_active_account(self.user, request=request), self.account_one)
        self.assertEqual(request.session[SESSION_KEY], self.account_one.pk)

    def test_stale_explicit_selection_fails_closed_without_account_fallback(self):
        request = self._request()
        request.session[SESSION_KEY] = self.account_one.pk
        self.account_one.status = 'disabled'
        self.account_one.save(update_fields=['status'])

        self.assertIsNone(get_active_account(self.user, request=request))
        self.assertNotIn(SESSION_KEY, request.session)

    def test_unknown_deriv_environment_cannot_become_active(self):
        account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="UNKNOWN-ENVIRONMENT",
            credentials={},
        )
        account.set_access_token("ci-test-token-unknown")
        account.save(update_fields=["access_token"])
        BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=account,
            status="connected",
        )
        request = self._request()
        request.session[SESSION_KEY] = account.pk

        # Unknown Deriv environment must be rejected by account-context selection.
        self.assertIsNone(get_active_account(self.user, request=request))
        self.assertNotIn(SESSION_KEY, request.session)

    def test_account_has_no_persistent_preference_field(self):
        self.assertNotIn('is_preferred', [field.name for field in BrokerAccount._meta.fields])
    def test_selection_and_connection_eligibility_are_canonical_model_contracts(self):
        # A connected, credential-ready Deriv account with a known environment
        # is eligible for selection and connection.
        self.assertTrue(self.account_one.is_selection_eligible)
        self.assertTrue(self.account_one.is_connection_eligible)

        # Connection is part of the explicit selection workflow, so a valid
        # OAuth account can be selected even before a BrokerConnection exists.
        pending = BrokerAccount.objects.create(
            user=self.user, broker=self.broker, account_id='DEMO-PENDING',
            credentials={'account_type': 'demo'},
        )
        pending.set_access_token('ci-test-token-pending')
        pending.save(update_fields=['access_token'])
        self.assertTrue(pending.is_selection_eligible)
        self.assertFalse(pending.is_connection_eligible)

        # Unknown Deriv environment is never eligible, even if a connection
        # row exists and credentials are otherwise decryptable.
        unknown = BrokerAccount.objects.create(
            user=self.user, broker=self.broker, account_id='UNKNOWN-PENDING',
            credentials={},
        )
        unknown.set_access_token('ci-test-token-unknown-eligibility')
        unknown.save(update_fields=['access_token'])
        BrokerConnection.objects.create(broker=self.broker, broker_account=unknown, status='connected')
        self.assertFalse(unknown.is_selection_eligible)
        self.assertFalse(unknown.is_connection_eligible)

    def test_serializer_exposes_server_owned_eligibility_and_snapshot_state(self):
        request = self._request()
        data = BrokerAccountSerializer(self.account_one, context={'request': request}).data
        self.assertTrue(data['selection_eligible'])
        self.assertTrue(data['connection_eligible'])
        self.assertFalse(data['snapshot_ready'])
        self.account_one.last_synced_at = timezone.now()
        self.account_one.save(update_fields=['last_synced_at'])
        data = BrokerAccountSerializer(self.account_one, context={'request': request}).data
        self.assertTrue(data['snapshot_ready'])
    def test_connected_account_without_authoritative_snapshot_is_not_active(self):
        request = self._request()
        self.assertIsNone(get_active_account(self.user, request=request))

    def test_expired_credentials_invalidate_explicit_server_selection(self):
        request = self._request()
        self.account_one.last_synced_at = timezone.now()
        self.account_one.save(update_fields=['last_synced_at'])
        request.session[SESSION_KEY] = self.account_one.pk
        self.account_one.token_status = 'expired'
        self.account_one.save(update_fields=['token_status'])
        self.assertIsNone(get_active_account(self.user, request=request))
        self.assertNotIn(SESSION_KEY, request.session)
    def test_connected_and_synchronized_account_is_not_active_without_explicit_session_selection(self):
        self.account_one.last_synced_at = timezone.now()
        self.account_one.save(update_fields=['last_synced_at'])
        request = self._request()
        self.assertIsNone(get_active_account(self.user, request=request))
        self.assertNotIn(SESSION_KEY, request.session)
    def test_explicit_selection_without_snapshot_is_cleared_instead_of_reused(self):
        request = self._request()
        request.session[SESSION_KEY] = self.account_one.pk
        self.assertIsNone(get_active_account(self.user, request=request))
        self.assertNotIn(SESSION_KEY, request.session)
