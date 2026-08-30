from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.utils import timezone

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection
from apps.execution.constants import ORDER_STATUS_QUEUED
from apps.execution.engine import ExecutionEngine
from apps.execution.models import Order


class AuthoritativeExecutionBoundaryTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='execution-account-boundary', password='test-pass')
        self.broker = Broker.objects.create(name='Deriv', broker_type='deriv', status='active', supports_live=True)
        self.old_account = self._account('VRTC-OLD', preferred=True)
        self.new_account = self._account('VRTC-NEW', preferred=False)

    def _account(self, account_id, preferred=False):
        account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id=account_id,
            status='active',
            is_preferred=preferred,
            credentials={'account_type': 'demo'},
            balance=Decimal('100'),
            equity=Decimal('100'),
            free_margin=Decimal('100'),
        )
        BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=account,
            status='connected',
            last_ping=timezone.now(),
            connected_at=timezone.now(),
        )
        return account

    def test_queued_order_is_blocked_after_account_switch(self):
        order = Order.objects.create(
            user=self.user,
            broker_account=self.old_account,
            symbol='R_100',
            direction='buy',
            order_type='market',
            stake=Decimal('1'),
            status=ORDER_STATUS_QUEUED,
        )

        self.old_account.is_preferred = False
        self.old_account.save(update_fields=['is_preferred'])
        self.new_account.is_preferred = True
        self.new_account.save(update_fields=['is_preferred'])

        adapter = SimpleNamespace(place_order=AsyncMock())
        with patch('apps.execution.engine.BrokerRegistry.adapter', return_value=adapter):
            with self.assertRaisesRegex(PermissionError, 'no longer the active account'):
                __import__('asyncio').run(ExecutionEngine().execute(order))

        adapter.place_order.assert_not_awaited()
        order.refresh_from_db()
        self.assertEqual(order.status, ORDER_STATUS_QUEUED)

    def test_active_account_is_required_for_order_creation(self):
        engine = ExecutionEngine()
        with self.assertRaisesRegex(PermissionError, 'no longer the active account'):
            engine.place_order(
                self.user,
                broker_account=self.new_account,
                symbol='R_100',
                direction='buy',
                order_type='market',
                stake=Decimal('1'),
            )
