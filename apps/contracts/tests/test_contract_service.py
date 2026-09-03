from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.broker.models import Broker, BrokerAccount
from apps.execution.models import Order
from apps.execution.services import PositionService, ContractService
class ContractServiceTests(TestCase):
    def test_purchase_contract(self):
        user=get_user_model().objects.create_user('c@example.com','c@example.com','pass'); broker=Broker.objects.create(name='CB',broker_type='deriv'); acct=BrokerAccount.objects.create(user=user,broker=broker,account_id='C')
        order=Order.objects.create(user=user,broker_account=acct,symbol='R_10',direction='buy',order_type='market',stake=1); pos=PositionService().open_position(order,Decimal('1'))
        contract=ContractService().purchase(pos,contract_id='CID',contract_type='rise_fall',buy_price=1,payout=2)
        self.assertEqual(contract.contract_id,'CID')
