from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from apps.brokers.models import Broker, BrokerAccount, BrokerConnection
from apps.execution.engine import ExecutionEngine
from apps.execution.models import Order, ExecutionQueue
from apps.risk.models import RiskProfile
class ExecutionEngineTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('u@example.com','u@example.com','pass')
        self.broker=Broker.objects.create(name='Test Broker',broker_type='deriv', status='active')
        self.account=BrokerAccount.objects.create(user=self.user,broker=self.broker,account_id='A1',balance=Decimal('100'),is_preferred=True,status='active')
        self.account.set_access_token('valid-token')
        self.account.token_status='active'
        self.account.expires_at=timezone.now() + timedelta(days=1)
        self.account.save(update_fields=['access_token','token_status','expires_at'])
        BrokerConnection.objects.create(broker=self.broker, broker_account=self.account, status='connected')
        RiskProfile.objects.create(user=self.user, max_risk_per_trade=Decimal('0.20'), max_exposure=Decimal('1.00'))
    def test_place_order_validates_and_queues(self):
        order=ExecutionEngine().place_order(self.user,broker_account=self.account,symbol='R_100',direction='buy',order_type='market',stake=Decimal('10'))
        self.assertEqual(order.status,'queued'); self.assertTrue(ExecutionQueue.objects.filter(order=order).exists())
