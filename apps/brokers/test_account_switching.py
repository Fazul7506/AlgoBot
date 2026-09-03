from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Broker, BrokerAccount, BrokerConnection
User=get_user_model()
class AccountSwitchingTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='account-switch-user',password='test-password'); self.client=APIClient(); self.client.force_authenticate(self.user)
        self.broker=Broker.objects.create(name='Paper Trading',broker_type='paper',status='active',supports_demo=True,supports_live=True,metadata={'auth':'none','avatar_url':'https://example.com/broker-avatar.png'})
    def make_account(self,account_id,account_type='demo',connected=True,status='active'):
        a=BrokerAccount.objects.create(user=self.user,broker=self.broker,account_id=account_id,is_preferred=False,status=status,credentials={'account_type':account_type})
        if connected: BrokerConnection.objects.create(broker=self.broker,broker_account=a,status='connected',last_ping=timezone.now(),connected_at=timezone.now())
        return a
    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_switch_changes_session_active_account_without_preferred_account(self):
        first=self.make_account('DEMO-1','demo'); second=self.make_account('REAL-2','real')
        result=self.client.post(f'/api/brokers/accounts/{second.pk}/select/',{},format='json')
        self.assertEqual(result.status_code,200); self.assertEqual(result.data['active_account_id'],second.pk)
        first.refresh_from_db(); second.refresh_from_db()
        self.assertFalse(first.is_preferred); self.assertTrue(second.is_preferred)
        self.assertEqual(BrokerAccount.objects.filter(user=self.user,is_preferred=True).count(),1)
        result=self.client.get('/api/brokers/accounts/active/')
        self.assertEqual(result.data['active_account_id'],second.pk)
        result=self.client.post(f'/api/brokers/accounts/{first.pk}/select/',{},format='json')
        self.assertEqual(result.status_code,200); self.assertEqual(result.data['active_account_id'],first.pk)
        self.assertEqual(self.client.get('/api/brokers/accounts/active/').data['active_account_id'],first.pk)
        first.refresh_from_db(); second.refresh_from_db(); self.assertTrue(first.is_preferred); self.assertFalse(second.is_preferred)
    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_demo_and_real_accounts_are_equally_selectable(self):
        demo=self.make_account('DEMO-1','demo'); real=self.make_account('REAL-1','real')
        for account in (demo,real):
            result=self.client.post(f'/api/brokers/accounts/{account.pk}/select/',{},format='json'); self.assertEqual(result.status_code,200); self.assertEqual(result.data['active_account_id'],account.pk)
    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_disconnected_account_cannot_become_active(self):
        candidate=self.make_account('DEMO-2',connected=False)
        result=self.client.post(f'/api/brokers/accounts/{candidate.pk}/select/',{},format='json')
        self.assertEqual(result.status_code,409); self.assertIn('not connected',result.data['detail'])
    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_inactive_account_cannot_become_active(self):
        candidate=self.make_account('DEMO-2',status='disabled')
        result=self.client.post(f'/api/brokers/accounts/{candidate.pk}/select/',{},format='json')
        self.assertEqual(result.status_code,409); self.assertIn('not active',result.data['detail'])
    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_wrong_environment_is_rejected_by_broker_verified_type(self):
        demo=self.make_account('DEMO-1','demo')
        result=self.client.post(f'/api/brokers/accounts/{demo.pk}/select/',{'account_type':'real'},format='json')
        self.assertEqual(result.status_code,409); self.assertIn('not real',result.data['detail'])
