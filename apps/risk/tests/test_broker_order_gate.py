from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.brokers.models import Broker, BrokerAccount, Order
from apps.risk.models import RiskAssessment
from apps.risk.services import KillSwitchService
from apps.risk.engine import RiskEngine


class BrokerOrderRiskGateTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('risk-gate@example.com', password='pass')
        self.broker = Broker.objects.create(name='Paper Trading', broker_type='paper', status='active')
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id='RISK-1',
            balance=Decimal('100000'),
        )

    def test_broker_order_is_assessed_by_risk_engine(self):
        order = Order.objects.create(
            user=self.user,
            broker=self.broker,
            account=self.account,
            symbol='R_100',
            direction='buy',
            stake=Decimal('10'),
        )
        assessment = RiskEngine().evaluate_order(order)
        self.assertTrue(assessment.approved)
        self.assertEqual(assessment.broker_trade_id, order.pk)
        self.assertEqual(RiskAssessment.objects.filter(broker_trade=order).count(), 1)

    def test_kill_switch_blocks_broker_order(self):
        KillSwitchService().activate(self.user, reason='audit test')
        order = Order.objects.create(
            user=self.user,
            broker=self.broker,
            account=self.account,
            symbol='R_100',
            direction='buy',
            stake=Decimal('10'),
        )
        assessment = RiskEngine().evaluate_order(order)
        self.assertFalse(assessment.approved)
        self.assertIn('Kill switch', assessment.rejection_reason)
