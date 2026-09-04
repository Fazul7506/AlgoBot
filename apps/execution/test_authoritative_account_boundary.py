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
        account.set_access_token(f'test-token-{account_id}')
        account.save(update_fields=['access_token'])
        BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=account,
            status='connected',
            last_ping=timezone.now(),
            connected_at=timezone.now(),
        )
        return account

    def test_execution_authority_is_not_derived_from_legacy_preferred_flag(self):
        self.old_account.is_preferred = False
        self.old_account.save(update_fields=['is_preferred'])
        self.new_account.is_preferred = True
        self.new_account.save(update_fields=['is_preferred'])

        order = Order.objects.create(
            user=self.user,
            broker_account=self.new_account,
            symbol='R_100',
            direction='buy',
            order_type='market',
            stake=Decimal('1'),
            status=ORDER_STATUS_QUEUED,
            validation_context={'execution_mode': 'manual_command'},
        )

        adapter = SimpleNamespace(place_order=AsyncMock(return_value={'broker_order_id': 'BROKER-1'}))
        with patch('apps.execution.engine.BrokerRegistry.adapter', return_value=adapter), \
             patch('apps.risk.engine.RiskEngine.approve_or_raise'):
            __import__('asyncio').run(ExecutionEngine().execute(order))

        adapter.place_order.assert_awaited_once()
        order.refresh_from_db()
        self.assertEqual(order.status, 'executed')
        self.assertEqual(order.broker_reference, 'BROKER-1')

    def test_explicit_connected_account_is_authoritative_for_order_creation(self):
        account = self.new_account
        engine = ExecutionEngine()
        self.assertIs(engine._assert_authoritative_account(self.user, account), account)
        self.assertFalse(account.is_preferred)

    def test_execution_rejects_account_from_another_user(self):
        other = get_user_model().objects.create_user(username='other-execution-user', password='test-pass')
        foreign = BrokerAccount.objects.create(
            user=other,
            broker=self.broker,
            account_id='FOREIGN-1',
            status='active',
            credentials={'account_type': 'demo'},
        )
        with self.assertRaisesRegex(PermissionError, 'does not belong to this user'):
            ExecutionEngine._assert_authoritative_account(self.user, foreign)
