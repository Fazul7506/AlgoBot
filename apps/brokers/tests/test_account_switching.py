from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.contrib.sessions.middleware import SessionMiddleware

from core.account_context import SESSION_KEY, get_active_account, select_account
from apps.brokers.models import Broker, BrokerAccount, BrokerConnection


class AccountSwitchingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='account-switch-user',
            password='test-password',
        )
        self.broker = Broker.objects.create(
            name='Paper Switching Test',
            broker_type='paper',
            status='active',
            supports_live=False,
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

        select_account(request, self.account_one)
        self.assertEqual(request.session[SESSION_KEY], self.account_one.pk)
        self.assertEqual(get_active_account(self.user, request=request), self.account_one)

        select_account(request, self.account_two)
        self.assertEqual(request.session[SESSION_KEY], self.account_two.pk)
        self.assertEqual(get_active_account(self.user, request=request), self.account_two)

    def test_query_parameter_can_select_an_account_on_normal_django_request(self):
        request = self._request(
            f'/api/brokers/accounts/active/?account_id={self.account_two.pk}'
        )
        self.assertEqual(get_active_account(self.user, request=request), self.account_two)

    def test_account_has_no_persistent_preference_field(self):
        self.assertNotIn('is_preferred', [field.name for field in BrokerAccount._meta.fields])
