from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.broker.models import Broker, BrokerAccount
from apps.execution.engine import ExecutionEngine
from apps.execution.models import Order, ExecutionQueue
class ExecutionEngineTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('u@example.com','u@example.com','pass')
        self.broker=Broker.objects.create(name='Test Broker',broker_type='deriv')
        self.account=BrokerAccount.objects.create(user=self.user,broker=self.broker,broker_account_id='A1',balance=Decimal('100'))
    def test_place_order_validates_and_queues(self):
        order=ExecutionEngine().place_order(self.user,broker_account=self.account,symbol='R_100',direction='buy',order_type='market',stake=Decimal('10'))
        self.assertEqual(order.status,'queued'); self.assertTrue(ExecutionQueue.objects.filter(order=order).exists())
