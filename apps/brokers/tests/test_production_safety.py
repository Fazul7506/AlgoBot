from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection, Order


class ProductionSafetyModelTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user_a = User.objects.create_user('audit-a@example.com', password='pass')
        self.user_b = User.objects.create_user('audit-b@example.com', password='pass')
        self.broker = Broker.objects.create(name='Paper Trading', broker_type='paper', status='active')
        self.account_a = BrokerAccount.objects.create(user=self.user_a, broker=self.broker, account_id='PAPER-A')
        self.account_b = BrokerAccount.objects.create(user=self.user_b, broker=self.broker, account_id='PAPER-B')

    def test_connection_is_scoped_to_account(self):
        first = BrokerConnection.objects.create(broker=self.broker, broker_account=self.account_a, status='connected')
        second = BrokerConnection.objects.create(broker=self.broker, broker_account=self.account_b, status='connected')
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(first.broker_account_id, self.account_a.pk)
        self.assertEqual(second.broker_account_id, self.account_b.pk)

    def test_client_order_id_is_unique_per_user_account(self):
        Order.objects.create(
            user=self.user_a,
            broker=self.broker,
            account=self.account_a,
            symbol='R_100',
            direction='buy',
            client_order_id='audit-123',
        )
        with self.assertRaises(IntegrityError):
            Order.objects.create(
                user=self.user_a,
                broker=self.broker,
                account=self.account_a,
                symbol='R_100',
                direction='buy',
                client_order_id='audit-123',
            )

    def test_same_client_order_id_is_allowed_on_different_accounts(self):
        Order.objects.create(
            user=self.user_a,
            broker=self.broker,
            account=self.account_a,
            symbol='R_100',
            direction='buy',
            client_order_id='same-key',
        )
        Order.objects.create(
            user=self.user_a,
            broker=self.broker,
            account=self.account_b,
            symbol='R_100',
            direction='buy',
            client_order_id='same-key',
        )
        self.assertEqual(Order.objects.filter(client_order_id='same-key').count(), 2)
