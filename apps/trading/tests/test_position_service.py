from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.broker.models import Broker, BrokerAccount
from apps.execution.models import Order
from apps.execution.services import PositionService
class PositionServiceTests(TestCase):
    def test_open_and_close_position(self):
        user=get_user_model().objects.create_user('p@example.com','p@example.com','pass'); broker=Broker.objects.create(name='B',broker_type='deriv'); acct=BrokerAccount.objects.create(user=user,broker=broker,account_id='P')
        order=Order.objects.create(user=user,broker_account=acct,symbol='R_50',direction='buy',order_type='market',stake=1)
        pos=PositionService().open_position(order,Decimal('10')); PositionService().close_position(pos,Decimal('12'))
        self.assertEqual(pos.status,'closed')
